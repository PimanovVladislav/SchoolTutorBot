from datetime import datetime
from html import escape
from pathlib import Path
import re

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.config import PROJECT_ROOT
from tutor_bot.db import repos
from tutor_bot.keyboards import (
    BTN_ADMIN,
    BTN_ADMIN_BACK,
    BTN_ADMIN_CONTENT,
    BTN_ADMIN_FLAGS,
    BTN_ADMIN_GRADE,
    BTN_ADMIN_GRANT,
    BTN_ADMIN_PROBLEM,
    BTN_ADMIN_STUDENTS,
    BTN_ADMIN_SUBJECT,
    BTN_ADMIN_THEORY_MORE,
    BTN_ADMIN_HINT_MORE,
    BTN_ADMIN_SOLUTION_MORE,
    BTN_ADMIN_TOPIC,
    BTN_CANCEL,
    AdminCB,
    admin_content_menu,
    admin_menu,
    admin_pick_keyboard,
    admin_user_actions,
    admin_users_keyboard,
    cancel_kb,
    menu_for,
    NAV_BUTTONS,
)
from tutor_bot.services.access import access_label, check_access, is_admin
from tutor_bot.services.scoring import MASTERY_LABELS
from tutor_bot.states import Admin

router = Router()


class AdminOnly(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user and is_admin(user.id))


router.message.filter(AdminOnly())
router.callback_query.filter(AdminOnly())


def _guess_answer_type(answer: str) -> str:
    raw = answer.strip()
    if ";" in raw or re.search(r"\bи\b", raw, re.IGNORECASE):
        return "numbers"
    if "/" in raw:
        return "fraction"
    if re.fullmatch(r"-?\d+([.,]\d+)?", raw):
        return "number"
    return "text"


async def _user_card(session: AsyncSession, user) -> str:
    info = await check_access(session, user)
    name = escape(user.first_name or user.username or "ученик")
    nick = f"@{escape(user.username)}" if user.username else "без ника"
    lines = [
        f"<b>{name}</b> · {nick}",
        f"id: <code>{user.id}</code>",
        f"Класс: {user.grade or '—'}",
        f"Доступ: {access_label(info)}",
    ]
    if user.track_id and user.grade:
        rows = await repos.list_progress_with_topics(
            session, user.id, user.track_id, user.grade
        )
        if rows:
            lines.append("")
            lines.append("<b>Прогресс</b>")
            for topic, progress in rows:
                if progress is None or progress.assessment_score is None:
                    lines.append(f"• {topic.title} — ещё не сдана")
                    continue
                mastery = MASTERY_LABELS.get(progress.mastery, progress.mastery)
                lines.append(
                    f"• {topic.title} — {progress.assessment_score:.0f}% ({mastery})"
                )
    return "\n".join(lines)


@router.message(F.text == BTN_ADMIN)
@router.message(Command("admin"))
async def open_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Админ-панель", reply_markup=admin_menu())


@router.message(F.text == BTN_ADMIN_BACK)
async def admin_back(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Меню ученика", reply_markup=menu_for(message.from_user.id))


@router.message(F.text == BTN_CANCEL)
async def admin_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменил.", reply_markup=admin_menu())


@router.message(F.text == BTN_ADMIN_CONTENT)
async def admin_content(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Что добавить?", reply_markup=admin_content_menu())


@router.message(F.text == BTN_ADMIN_SUBJECT)
async def add_subject_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Admin.subject_title)
    await message.answer("Название предмета:", reply_markup=cancel_kb())


@router.message(Admin.subject_title, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_subject_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    title = (message.text or "").strip()
    if title in {BTN_CANCEL, BTN_ADMIN_BACK} or not title:
        return
    subject = await repos.create_subject(session, title)
    await state.clear()
    await message.answer(
        f"Предмет «{escape(subject.title)}» создан, трек «Школьная программа» добавлен.",
        reply_markup=admin_content_menu(),
    )


@router.message(F.text == BTN_ADMIN_GRADE)
async def add_grade_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Admin.grade_number)
    await message.answer("Номер класса (число), например 10:", reply_markup=cancel_kb())


@router.message(Admin.grade_number, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_grade_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip()
    if raw in {BTN_CANCEL, BTN_ADMIN_BACK}:
        return
    try:
        grade = int(raw)
    except ValueError:
        await message.answer("Нужно целое число.")
        return
    if grade < 1 or grade > 11:
        await message.answer("Класс должен быть от 1 до 11.")
        return
    await repos.add_grade(session, grade)
    await state.clear()
    await message.answer(f"{grade} класс добавлен в список.", reply_markup=admin_content_menu())


@router.message(F.text == BTN_ADMIN_TOPIC)
async def add_topic_start(message: Message, state: FSMContext, session: AsyncSession) -> None:
    subjects = await repos.list_subjects(session)
    if not subjects:
        await message.answer("Сначала добавь предмет.")
        return
    await state.update_data(wizard="topic")
    await message.answer(
        "Выбери предмет:",
        reply_markup=admin_pick_keyboard(
            "topic_subj", [(s.id, s.title) for s in subjects]
        ),
    )


@router.callback_query(AdminCB.filter(F.a == "topic_subj"))
async def add_topic_subject(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    grades = await repos.list_grades(session)
    await state.update_data(subject_id=callback_data.i)
    await callback.message.answer(
        "Класс темы:",
        reply_markup=admin_pick_keyboard("topic_grade", [(g, f"{g} класс") for g in grades]),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.a == "topic_grade"))
async def add_topic_grade(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    await state.update_data(grade=callback_data.i)
    await state.set_state(Admin.topic_title)
    await callback.message.answer("Название темы:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(Admin.topic_title, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_topic_title(message: Message, state: FSMContext) -> None:
    title = (message.text or "").strip()
    if title in {BTN_CANCEL, BTN_ADMIN_BACK} or not title:
        return
    await state.update_data(title=title)
    await state.set_state(Admin.topic_summary)
    await message.answer("Краткое описание темы (или «-»):")


@router.message(Admin.topic_summary, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_topic_summary(message: Message, state: FSMContext) -> None:
    summary = (message.text or "").strip()
    if summary == "-":
        summary = ""
    await state.update_data(summary=summary)
    await state.set_state(Admin.topic_theory)
    await state.update_data(theories=[])
    await message.answer(
        "Теория, редакция 1: текст одним сообщением или фото. "
        "Если теорий несколько — после первой пришли следующую. «-» — закончить."
    )


async def _ask_more_theory(message: Message, state: FSMContext, item: dict) -> None:
    theories = list((await state.get_data()).get("theories") or [])
    theories.append(item)
    await state.update_data(theories=theories)
    await message.answer(
        f"Редакция {len(theories)} сохранена. Пришли ещё объяснение или «-», "
        "чтобы перейти к числу заданий в проверочной."
    )


async def _go_topic_assessment(message: Message, state: FSMContext) -> None:
    await state.set_state(Admin.topic_assessment)
    await message.answer("Сколько заданий в проверочной? Число, например 3.")


@router.message(Admin.topic_theory, F.photo)
async def add_topic_theory_photo(
    message: Message, state: FSMContext
) -> None:
    photo = message.photo[-1]
    folder = PROJECT_ROOT / "media" / "theory"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"admin-{int(datetime.utcnow().timestamp())}.jpg"
    dest = folder / filename
    await message.bot.download(photo, destination=dest)
    await _ask_more_theory(
        message,
        state,
        {
            "body": "",
            "kind": "photo",
            "image_path": str(Path("media") / "theory" / filename),
        },
    )


@router.message(Admin.topic_theory, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_topic_theory_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text in {BTN_CANCEL, BTN_ADMIN_BACK}:
        return
    if text == "-":
        await _go_topic_assessment(message, state)
        return
    await _ask_more_theory(
        message,
        state,
        {"body": text, "kind": "text", "image_path": None},
    )


@router.message(Admin.topic_assessment, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_topic_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    raw = (message.text or "").strip()
    try:
        required = int(raw)
    except ValueError:
        await message.answer("Нужно число.")
        return
    data = await state.get_data()
    track = await repos.default_track_for_subject(session, data["subject_id"])
    if track is None:
        await state.clear()
        await message.answer("У предмета нет трека.", reply_markup=admin_content_menu())
        return
    theories = list(data.get("theories") or [])
    first = theories[0] if theories else {}
    topic = await repos.create_topic(
        session,
        track_id=track.id,
        grade=int(data["grade"]),
        title=data["title"],
        summary=data.get("summary") or "",
        theory=first.get("body") or "",
        theory_kind=first.get("kind") or "text",
        theory_image_path=first.get("image_path"),
        assessment_required=required,
    )
    for extra in theories[1:]:
        await repos.add_topic_theory(
            session,
            topic.id,
            body=extra.get("body") or "",
            kind=extra.get("kind") or "text",
            image_path=extra.get("image_path"),
        )
    await state.clear()
    await message.answer(
        f"Тема «{escape(topic.title)}» сохранена, id {topic.id}, "
        f"редакций теории: {len(theories)}.",
        reply_markup=admin_content_menu(),
    )


@router.message(F.text == BTN_ADMIN_THEORY_MORE)
@router.message(F.text == BTN_ADMIN_HINT_MORE)
@router.message(F.text == BTN_ADMIN_SOLUTION_MORE)
async def extra_edition_start(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    subjects = await repos.list_subjects(session)
    if not subjects:
        await message.answer("Сначала добавь предмет и тему.")
        return
    wizard = {
        BTN_ADMIN_THEORY_MORE: "theory_more",
        BTN_ADMIN_HINT_MORE: "hint_more",
        BTN_ADMIN_SOLUTION_MORE: "solution_more",
    }[message.text]
    await state.clear()
    await state.update_data(wizard=wizard)
    await message.answer(
        "Предмет:",
        reply_markup=admin_pick_keyboard(
            "prob_subj", [(s.id, s.title) for s in subjects]
        ),
    )


@router.message(F.text == BTN_ADMIN_PROBLEM)
async def add_problem_start(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    subjects = await repos.list_subjects(session)
    if not subjects:
        await message.answer("Сначала добавь предмет и тему.")
        return
    await state.clear()
    await state.update_data(wizard="problem")
    await message.answer(
        "Предмет задания:",
        reply_markup=admin_pick_keyboard(
            "prob_subj", [(s.id, s.title) for s in subjects]
        ),
    )


@router.callback_query(AdminCB.filter(F.a == "prob_subj"))
async def add_problem_subject(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    grades = await repos.list_grades(session)
    await state.update_data(subject_id=callback_data.i)
    await callback.message.answer(
        "Класс:",
        reply_markup=admin_pick_keyboard("prob_grade", [(g, f"{g} класс") for g in grades]),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.a == "prob_grade"))
async def add_problem_grade(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    track = await repos.default_track_for_subject(session, data["subject_id"])
    if track is None:
        await callback.answer("Нет трека", show_alert=True)
        return
    topics = await repos.list_topics_for_grade(session, track.id, callback_data.i)
    if not topics:
        await callback.answer("В этом классе нет тем", show_alert=True)
        return
    await callback.message.answer(
        "Тема:",
        reply_markup=admin_pick_keyboard(
            "prob_topic", [(t.id, t.title) for t in topics]
        ),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.a == "prob_topic"))
async def add_problem_topic(
    callback: CallbackQuery,
    callback_data: AdminCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(topic_id=callback_data.i)
    wizard = (await state.get_data()).get("wizard")
    if wizard == "theory_more":
        await state.set_state(Admin.extra_theory)
        await callback.message.answer(
            "Текст или фото новой редакции теории:",
            reply_markup=cancel_kb(),
        )
        await callback.answer()
        return
    if wizard in {"hint_more", "solution_more"}:
        problems = await repos.list_topic_problems(session, callback_data.i)
        if not problems:
            await callback.answer("В теме нет заданий", show_alert=True)
            return
        buttons = []
        for problem in problems:
            preview = problem.prompt.replace("\n", " ")[:40]
            buttons.append((problem.id, f"#{problem.id} {preview}"))
        await callback.message.answer(
            "Задание:",
            reply_markup=admin_pick_keyboard("ext_prob", buttons),
        )
        await callback.answer()
        return
    await callback.message.answer(
        "Тип задания:",
        reply_markup=admin_pick_keyboard(
            "prob_kind",
            [
                (1, "тренировка"),
                (2, "проверочная"),
                (3, "закрепление"),
            ],
        ),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.a == "ext_prob"))
async def extra_pick_problem(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    wizard = (await state.get_data()).get("wizard")
    await state.update_data(problem_id=callback_data.i)
    if wizard == "hint_more":
        await state.set_state(Admin.extra_hint)
        await callback.message.answer("Текст новой подсказки:", reply_markup=cancel_kb())
    else:
        await state.set_state(Admin.extra_solution)
        await callback.message.answer("Текст нового разбора:", reply_markup=cancel_kb())
    await callback.answer()


@router.callback_query(AdminCB.filter(F.a == "prob_kind"))
async def add_problem_kind(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    kinds = {1: "training", 2: "assessment", 3: "reinforcement"}
    await state.update_data(kind=kinds.get(callback_data.i, "training"))
    await callback.message.answer(
        "Сложность:",
        reply_markup=admin_pick_keyboard(
            "prob_diff",
            [(1, "1 · лёгкий"), (2, "2 · средний"), (3, "3 · сложный")],
        ),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.a == "prob_diff"))
async def add_problem_diff(
    callback: CallbackQuery, callback_data: AdminCB, state: FSMContext
) -> None:
    await state.update_data(difficulty=callback_data.i)
    await state.set_state(Admin.problem_prompt)
    await callback.message.answer("Текст задания:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(Admin.problem_prompt, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_problem_prompt(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text in {BTN_CANCEL, BTN_ADMIN_BACK} or not text:
        return
    await state.update_data(prompt=text)
    await state.set_state(Admin.problem_answer)
    await message.answer("Правильный ответ (как должен написать ученик):")


@router.message(Admin.problem_answer, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_problem_answer(message: Message, state: FSMContext) -> None:
    await state.update_data(correct_answer=(message.text or "").strip(), hints=[])
    await state.set_state(Admin.problem_hint)
    await message.answer("Подсказка 1 (или «-», если без подсказок):")


@router.message(Admin.problem_hint, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_problem_hint(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    hints = list((await state.get_data()).get("hints") or [])
    if text == "-":
        await state.update_data(hints=hints, solutions=[])
        await state.set_state(Admin.problem_solution)
        await message.answer("Разбор 1 (или «-», если без разбора):")
        return
    if not text:
        return
    hints.append(text)
    await state.update_data(hints=hints)
    await message.answer(
        f"Подсказка {len(hints)} сохранена. Ещё подсказка или «-»."
    )


@router.message(Admin.problem_solution, F.text, ~F.text.in_(NAV_BUTTONS))
async def add_problem_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    text = (message.text or "").strip()
    solutions = list((await state.get_data()).get("solutions") or [])
    if text != "-":
        if not text:
            return
        solutions.append(text)
        await state.update_data(solutions=solutions)
        await message.answer(
            f"Разбор {len(solutions)} сохранён. Ещё разбор или «-»."
        )
        return
    data = await state.get_data()
    answer = data.get("correct_answer") or ""
    hints = list(data.get("hints") or [])
    problem = await repos.create_problem(
        session,
        topic_id=int(data["topic_id"]),
        kind=data.get("kind") or "training",
        difficulty=int(data.get("difficulty") or 1),
        prompt=data.get("prompt") or "",
        correct_answer=answer,
        hint="",
        solution="",
        hints=hints,
        solutions=solutions,
        answer_type=_guess_answer_type(answer),
    )
    await state.clear()
    await message.answer(
        f"Задание #{problem.id} сохранено. "
        f"Подсказок: {len(hints)}, разборов: {len(solutions)}.",
        reply_markup=admin_content_menu(),
    )


@router.message(Admin.extra_theory, F.photo)
async def extra_theory_photo(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if not topic_id:
        await message.answer("Тема не выбрана.", reply_markup=admin_content_menu())
        return
    photo = message.photo[-1]
    folder = PROJECT_ROOT / "media" / "theory"
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"admin-{int(datetime.utcnow().timestamp())}.jpg"
    dest = folder / filename
    await message.bot.download(photo, destination=dest)
    row = await repos.add_topic_theory(
        session,
        int(topic_id),
        body="",
        kind="photo",
        image_path=str(Path("media") / "theory" / filename),
    )
    await state.clear()
    await message.answer(
        f"Редакция {row.edition} из {row.edition_count} добавлена.",
        reply_markup=admin_content_menu(),
    )


@router.message(Admin.extra_theory, F.text, ~F.text.in_(NAV_BUTTONS))
async def extra_theory_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    text = (message.text or "").strip()
    if text in {BTN_CANCEL, BTN_ADMIN_BACK, "-"} or not text:
        return
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if not topic_id:
        await message.answer("Тема не выбрана.", reply_markup=admin_content_menu())
        return
    row = await repos.add_topic_theory(
        session, int(topic_id), body=text, kind="text"
    )
    await state.clear()
    await message.answer(
        f"Редакция {row.edition} из {row.edition_count} добавлена.",
        reply_markup=admin_content_menu(),
    )


@router.message(Admin.extra_hint, F.text, ~F.text.in_(NAV_BUTTONS))
async def extra_hint_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    text = (message.text or "").strip()
    if text in {BTN_CANCEL, BTN_ADMIN_BACK, "-"} or not text:
        return
    data = await state.get_data()
    problem_id = data.get("problem_id")
    if not problem_id:
        await message.answer("Задание не выбрано.", reply_markup=admin_content_menu())
        return
    row = await repos.add_problem_hint(session, int(problem_id), text)
    await state.clear()
    await message.answer(
        f"Подсказка {row.edition} из {row.edition_count} добавлена к заданию #{problem_id}.",
        reply_markup=admin_content_menu(),
    )


@router.message(Admin.extra_solution, F.text, ~F.text.in_(NAV_BUTTONS))
async def extra_solution_save(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    text = (message.text or "").strip()
    if text in {BTN_CANCEL, BTN_ADMIN_BACK, "-"} or not text:
        return
    data = await state.get_data()
    problem_id = data.get("problem_id")
    if not problem_id:
        await message.answer("Задание не выбрано.", reply_markup=admin_content_menu())
        return
    row = await repos.add_problem_solution(session, int(problem_id), text)
    await state.clear()
    await message.answer(
        f"Разбор {row.edition} из {row.edition_count} добавлен к заданию #{problem_id}.",
        reply_markup=admin_content_menu(),
    )


@router.message(F.text == BTN_ADMIN_STUDENTS)
async def list_students(message: Message, session: AsyncSession) -> None:
    await _send_students_page(message, session, 0)


@router.callback_query(AdminCB.filter(F.a == "users"))
async def list_students_page(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await _send_students_page(callback.message, session, callback_data.i)
    await callback.answer()


async def _send_students_page(message: Message, session: AsyncSession, offset: int) -> None:
    total = await repos.count_users(session)
    users = await repos.list_users_page(session, offset=offset, limit=6)
    if not users:
        await message.answer("Учеников пока нет.")
        return
    lines = [f"<b>Ученики</b> · {total} чел.\n"]
    buttons: list[tuple[int, str]] = []
    for user in users:
        info = await check_access(session, user)
        nick = f"@{user.username}" if user.username else str(user.id)
        name = user.first_name or "без имени"
        lines.append(
            f"• {escape(name)} · {escape(nick)} · {user.grade or '—'} кл. · {access_label(info)}"
        )
        buttons.append((user.id, f"{name} · {nick}"))
    await message.answer("\n".join(lines), reply_markup=admin_pick_keyboard("user", buttons))
    await message.answer(
        "Страницы:",
        reply_markup=admin_users_keyboard(offset, offset + 6 < total),
    )


@router.callback_query(AdminCB.filter(F.a == "user"))
async def show_student(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    user = await repos.get_user(session, callback_data.i)
    if user is None:
        await callback.answer("Нет такого ученика", show_alert=True)
        return
    await callback.message.answer(
        await _user_card(session, user),
        reply_markup=admin_user_actions(user.id),
    )
    await callback.answer()


@router.callback_query(AdminCB.filter(F.a == "grant30"))
async def grant_student(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    user = await repos.get_user(session, callback_data.i)
    if user is None:
        await callback.answer("Нет такого ученика", show_alert=True)
        return
    sub = await repos.grant_subscription(
        session, user.id, 30, source="admin", now=datetime.utcnow()
    )
    await callback.message.answer(
        f"Доступ {user.id} до {sub.ends_at.strftime('%d.%m.%Y')}."
    )
    try:
        await callback.bot.send_message(
            user.id,
            f"Доступ открыт до {sub.ends_at.strftime('%d.%m.%Y')}.",
            reply_markup=menu_for(user.id),
        )
    except Exception:
        pass
    await callback.answer("Выдано")


@router.callback_query(AdminCB.filter(F.a == "revoke"))
async def revoke_student(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await repos.revoke_subscriptions(session, callback_data.i)
    await callback.message.answer(f"Доступ {callback_data.i} отозван.")
    await callback.answer("Отозвано")


@router.message(F.text == BTN_ADMIN_GRANT)
async def grant_start(message: Message, state: FSMContext) -> None:
    await state.set_state(Admin.grant_target)
    await message.answer(
        "Пришли id, @username или перешли сообщение ученика.",
        reply_markup=cancel_kb(),
    )


@router.message(Admin.grant_target, F.forward_from)
async def grant_from_forward(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    src = message.forward_from
    await repos.upsert_user(
        session, src.id, src.username, src.first_name, src.last_name
    )
    await state.update_data(grant_user_id=src.id)
    await state.set_state(Admin.grant_days)
    await message.answer("На сколько дней выдать доступ?")


@router.message(Admin.grant_target, F.text, ~F.text.in_(NAV_BUTTONS))
async def grant_from_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    raw = (message.text or "").strip()
    if raw in {BTN_CANCEL, BTN_ADMIN_BACK}:
        return
    user = await repos.find_user(session, raw)
    if user is None and raw.lstrip("-").isdigit():
        user = await repos.upsert_user(session, int(raw), None, None, None)
    if user is None:
        await message.answer(
            "Пользователь не найден. Он должен хотя бы раз нажать /start."
        )
        return
    await state.update_data(grant_user_id=user.id)
    await state.set_state(Admin.grant_days)
    await message.answer(f"Нашёл {user.id}. На сколько дней выдать доступ?")


@router.message(Admin.grant_days, F.text, ~F.text.in_(NAV_BUTTONS))
async def grant_save(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        days = int((message.text or "").strip())
    except ValueError:
        await message.answer("Нужно число дней.")
        return
    data = await state.get_data()
    user_id = int(data["grant_user_id"])
    sub = await repos.grant_subscription(
        session, user_id, days, source="admin", now=datetime.utcnow()
    )
    await state.clear()
    await message.answer(
        f"Доступ {user_id} до {sub.ends_at.strftime('%d.%m.%Y')}.",
        reply_markup=admin_menu(),
    )
    try:
        await message.bot.send_message(
            user_id,
            f"Доступ открыт до {sub.ends_at.strftime('%d.%m.%Y')}.",
            reply_markup=menu_for(user_id),
        )
    except Exception:
        pass


@router.message(F.text == BTN_ADMIN_FLAGS)
async def list_flags(message: Message, session: AsyncSession) -> None:
    problems = await repos.list_flagged_problems(session)
    if not problems:
        await message.answer("Жалоб нет.", reply_markup=admin_menu())
        return
    builder_items: list[tuple[int, str]] = []
    lines = ["<b>Задания на проверку</b>\n"]
    for problem in problems:
        preview = problem.prompt.replace("\n", " ")[:80]
        lines.append(f"#{problem.id} · {escape(preview)}")
        builder_items.append((problem.id, f"Снять флаг #{problem.id}"))
    await message.answer("\n".join(lines))
    await message.answer(
        "Снять отметку:",
        reply_markup=admin_pick_keyboard("unflag", builder_items),
    )


@router.callback_query(AdminCB.filter(F.a == "unflag"))
async def unflag_problem(
    callback: CallbackQuery, callback_data: AdminCB, session: AsyncSession
) -> None:
    await repos.clear_problem_flag(session, callback_data.i)
    await callback.message.answer(f"Флаг с задания #{callback_data.i} снят.")
    await callback.answer("Готово")
