from datetime import datetime, timedelta
from html import escape
import re

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.config import ASSESSMENT_HOURS
from tutor_bot.db import repos
from tutor_bot.handlers.common import ensure_user, require_access
from tutor_bot.keyboards import (
    BTN_APPEAL,
    BTN_BACK,
    BTN_CHANGE_CLASS,
    BTN_CONTINUE,
    BTN_EXAM_FINISH,
    BTN_EXAM_START,
    BTN_HOME,
    BTN_PROGRESS,
    BTN_SCHEDULE,
    BTN_SETTINGS,
    BTN_SUB,
    NAV_BUTTONS,
    MenuCB,
    exam_reply_keyboard,
    exam_result_reply_keyboard,
    exam_start_reply_keyboard,
    learn_reply_keyboard,
    learn_status_note,
    menu_for,
    parse_exam_result_button,
    parse_exam_task_button,
    parse_start_from_button,
    passed_status_note,
    section_for,
    settings_reply_keyboard,
    subject_keyboard,
    topics_catalog_html,
    theory_reply_keyboard,
    training_reply_keyboard,
)
from tutor_bot.services.access import is_admin
from tutor_bot.services.answers import check_answer
from tutor_bot.services.chat import delete_quietly, remember_exam_panel
from tutor_bot.services.grades import (
    assessment_size,
    better_grade,
    exam_rules_text,
    format_dt,
    is_passed,
    score_to_grade,
)
from tutor_bot.services.learning import pick_assessment_queue
from tutor_bot.services import nav
from tutor_bot.services.richtext import send_rich
from tutor_bot.states import Learn, Onboarding

router = Router()

STUBS = {
    1: "Раздел «Подписка» скоро появится.",
    2: "Раздел «Оставить обращение» скоро появится.",
    3: "Раздел «Расписание» скоро появится.",
}


def _now() -> datetime:
    return datetime.utcnow()


async def _safe_edit(target: Message, text: str, markup) -> Message:
    try:
        await target.edit_text(text, reply_markup=markup)
        return target
    except TelegramBadRequest:
        return await target.bot.send_message(
            target.chat.id, text, reply_markup=markup
        )


async def _present(
    target: Message,
    state: FSMContext,
    text: str,
    markup=None,
    *,
    edit: bool = False,
    user_id: int | None = None,
) -> Message:
    uid = user_id or target.chat.id
    if edit:
        inline = markup if isinstance(markup, InlineKeyboardMarkup) else None
        sent = await _safe_edit(target, text, inline)
        await nav.attach_ids(state, [sent.message_id])
        return sent
    if isinstance(markup, InlineKeyboardMarkup):
        sent = await target.answer(text, reply_markup=markup)
        await nav.attach_ids(state, [sent.message_id])
        return sent
    kb = markup if isinstance(markup, ReplyKeyboardMarkup) else section_for(uid)
    sent = await target.answer(text, reply_markup=kb)
    await nav.attach_ids(state, [sent.message_id])
    await nav.adopt_reply_kb(target.bot, target.chat.id, state, sent.message_id)
    return sent


RESULT_LIMIT = 3900


def _answer_status(row) -> str:
    if row.is_correct:
        return "верно"
    if (row.submitted or "").strip():
        return "неверно"
    return "нет ответа"


async def _restore_section_reply(
    target: Message,
    state: FSMContext,
    user_id: int,
    screen: dict,
    *,
    force: bool = False,
) -> None:
    kb = await _section_kb_for(state, user_id, screen)
    if kb is None:
        return
    captions = {
        "learn": "Обучение. Выбери действие:",
        "progress": "Прогресс. Выбери действие:",
        "settings": "Настройки. Выбери действие:",
        "theory": "Теория. Выбери действие:",
        "training": "Тренировка. Выбери действие:",
        "exam_info": "Проверочная. Выбери действие:",
        "exam_result": "Результат. Выбери действие:",
        "history": "История. Выбери действие:",
    }
    await nav.apply_reply_keyboard(
        target,
        state,
        kb,
        force=force,
        caption=captions.get(screen.get("s"), "Выбери действие:"),
    )


async def _section_kb_for(state: FSMContext, user_id: int, screen: dict):
    kind = screen.get("s")
    admin = is_admin(user_id)
    data = await state.get_data()
    if kind == "learn":
        number = int(data.get("start_number") or 1)
        return learn_reply_keyboard(number, admin=admin)
    if kind == "settings":
        return settings_reply_keyboard(admin=admin)
    if kind == "theory":
        return theory_reply_keyboard(can_more=True, admin=admin)
    if kind == "training":
        return training_reply_keyboard(
            can_level_up=bool(data.get("can_level_up")),
            can_level_down=bool(data.get("can_level_down")),
            admin=admin,
        )
    if kind == "exam_info":
        return exam_start_reply_keyboard(admin=admin)
    if kind == "exam_work":
        return None
    if kind == "exam_result":
        return section_for(user_id)
    return section_for(user_id)


def _exam_kb(user_id: int, answers):
    return exam_reply_keyboard(answers, admin=is_admin(user_id))


async def _wipe_exam_question(bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    ids = list(data.get("exam_question_ids") or [])
    await delete_quietly(bot, chat_id, ids)
    await nav.forget_reply_kb_if_deleted(state, ids)
    await state.update_data(exam_question_ids=[])


async def _forget_exam_panel(bot, chat_id: int, state: FSMContext, attempt=None) -> None:
    data = await state.get_data()
    ids = list(data.get("exam_panel_ids") or [])
    if attempt is not None and attempt.panel_message_id:
        ids.append(attempt.panel_message_id)
        attempt.panel_message_id = None
    await delete_quietly(bot, chat_id, ids)
    await nav.forget_reply_kb_if_deleted(state, ids)
    await state.update_data(exam_panel_ids=[])


async def _require_student(
    session: AsyncSession, tg_user, target: Message
):
    user = await ensure_user(session, tg_user)
    if user.grade is None or user.track_id is None:
        return user, "choose"
    denied = await require_access(session, user)
    if denied:
        await target.answer(denied, reply_markup=menu_for(user.id))
        return user, "denied"
    return user, None


async def show_learn_list(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    *,
    edit: bool = False,
) -> None:
    await nav.reset_stack(state, {"s": "learn"})
    rows = await repos.list_progress_with_topics(
        session, user.id, user.track_id, user.grade
    )
    attempts = await repos.list_attempts_for_topics(
        session, user.id, [topic.id for topic, _ in rows]
    )
    by_topic: dict[int, list] = {}
    for item in attempts:
        by_topic.setdefault(item.topic_id, []).append(item)
    visible = []
    for topic, progress in rows:
        if is_passed(progress.best_grade if progress else None):
            continue
        topic_attempts = by_topic.get(topic.id) or []
        started = bool(
            (progress and (progress.theory_done or progress.training_done))
            or topic_attempts
        )
        active = next(
            (item for item in topic_attempts if item.status == "in_progress"),
            None,
        )
        label = None
        if active:
            label = "идёт"
        elif started:
            finished = sorted(
                (item for item in topic_attempts if item.grade),
                key=lambda item: item.id,
            )
            label = finished[-1].grade if finished else "…"
        visible.append((topic, label))
    text = (
        f"<b>Продолжить обучение</b>\n"
        f"{user.grade} класс. Темы, которые ещё не сданы на 3 и выше."
    )
    await state.set_state(Learn.pick_topic)
    await state.update_data(pick_source="learn")
    if visible:
        catalog = topics_catalog_html(
            [
                (topic.sort_order, topic.title, learn_status_note(label))
                for topic, label in visible
            ]
        )
        first = min(visible, key=lambda item: (item[0].sort_order, item[0].id))
        start_topic, _ = first
        text += (
            f"\n\n{catalog}\n\n"
            "Нажми «Начать», чтобы перейти к изучению по порядку "
            "или напиши номер темы, к которой хочешь приступить."
        )
        await state.update_data(
            start_topic_id=start_topic.id,
            start_number=start_topic.sort_order,
        )
        markup = learn_reply_keyboard(
            start_topic.sort_order, admin=is_admin(user.id)
        )
    else:
        text += "\n\nВсе темы этого класса уже сданы — посмотри «Мой прогресс»."
        markup = None
    await _present(target, state, text, markup, edit=edit)


async def show_progress_list(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    *,
    edit: bool = False,
) -> None:
    await nav.reset_stack(state, {"s": "progress"})
    rows = await repos.list_progress_with_topics(
        session, user.id, user.track_id, user.grade
    )
    passed = [
        (topic, progress.best_grade)
        for topic, progress in rows
        if progress and is_passed(progress.best_grade)
    ]
    text = (
        f"<b>Мой прогресс</b>\n"
        f"{user.grade} класс. Темы с оценкой 3 и выше."
    )
    await state.set_state(Learn.pick_topic)
    await state.update_data(pick_source="progress")
    if passed:
        catalog = topics_catalog_html(
            [
                (topic.sort_order, topic.title, passed_status_note(grade))
                for topic, grade in passed
            ]
        )
        text += (
            f"\n\n{catalog}\n\n"
            "Напиши номер темы, чтобы открыть теорию. "
            "Для истории сдач напиши «и» и номер, например: и1."
        )
        markup = None
    else:
        text += "\n\nПока нет успешно сданных тем."
        markup = None
    await _present(target, state, text, markup, edit=edit)


async def show_settings(
    target: Message, state: FSMContext, *, edit: bool = False
) -> None:
    await nav.reset_stack(state, {"s": "settings"})
    text = "<b>Настройки</b>\nВыбери действие."
    await _present(
        target, state, text, settings_reply_keyboard(admin=is_admin(target.chat.id)), edit=edit
    )


async def _open_theory(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    topic_id: int,
) -> None:
    from tutor_bot.handlers.learn import show_topic_theory

    topic = await repos.get_topic(session, topic_id)
    if topic is None:
        await target.answer("Тема не найдена.")
        return
    stack = await nav.get_stack(state)
    if stack and stack[-1].get("s") == "theory":
        await delete_quietly(target.bot, target.chat.id, stack[-1].get("ids") or [])
        await nav.replace_top(state, {"s": "theory", "t": topic_id})
    else:
        await nav.goto(state, {"s": "theory", "t": topic_id})
    await show_topic_theory(target, state, session, user, topic)


async def _maybe_expire(
    session: AsyncSession, attempt, now: datetime
) -> object:
    if attempt is None or attempt.status != "in_progress":
        return attempt
    if attempt.deadline_at and now >= attempt.deadline_at:
        await _complete_attempt(session, attempt, now=now, status="expired")
    return attempt


async def _complete_attempt(
    session: AsyncSession, attempt, *, now: datetime, status: str
) -> None:
    answers = await repos.get_attempt_answers(session, attempt.id)
    problems = {
        item.id: item
        for item in await repos.get_problems_by_ids(
            session, [row.problem_id for row in answers]
        )
    }
    correct = 0
    for row in answers:
        problem = problems.get(row.problem_id)
        submitted = (row.submitted or "").strip()
        ok = bool(
            problem
            and submitted
            and check_answer(problem.answer_type, problem.correct_answer, submitted)
        )
        row.is_correct = ok
        if ok:
            correct += 1
    prev_max = await repos.count_max_scores(
        session, attempt.user_id, attempt.topic_id, exclude_id=attempt.id
    )
    streak = prev_max + (1 if attempt.total and correct == attempt.total else 0)
    grade = score_to_grade(correct, attempt.total, max_streak=streak)
    await repos.finish_attempt(
        session,
        attempt,
        finished_at=now,
        status=status,
        correct_count=correct,
        grade=grade,
    )
    progress = await repos.get_or_create_progress(
        session, attempt.user_id, attempt.topic_id
    )
    progress.best_grade = better_grade(progress.best_grade, grade)
    if attempt.total:
        progress.assessment_score = round(100.0 * correct / attempt.total, 1)
    progress.training_done = True
    progress.mastery = "mastered" if is_passed(grade) else "needs_practice"


def _result_text(topic_title: str, attempt) -> str:
    extra = ""
    if attempt.status == "expired":
        extra = "\nРабота завершена автоматически: время вышло."
    return (
        f'Проверочная работа по теме «{topic_title}»\n\n'
        f"Дата выполнения:\n"
        f"с {format_dt(attempt.started_at)}\n"
        f"по {format_dt(attempt.finished_at)}\n\n"
        f"Верно решено: {attempt.correct_count} из {attempt.total}\n"
        f"Оценка: {attempt.grade}{extra}"
    )


async def _expanded_section(session: AsyncSession, row) -> str:
    problem = await repos.get_problem(session, row.problem_id)
    if problem is None:
        return f"\n\n────────\nЗадание {row.sort_order} не найдено."
    solutions = await repos.list_solution_bodies(session, problem)
    solution = solutions[0] if solutions else (problem.solution or "—")
    submitted = escape((row.submitted or "").strip() or "—")
    prompt = problem.prompt or "—"
    return (
        f"\n\n────────\n"
        f"<b>Задание {row.sort_order}</b> — {_answer_status(row)}\n"
        f"{prompt}\n\n"
        f"Твой ответ: <code>{submitted}</code>\n"
        f"<b>Правильное решение</b>\n{solution}"
    )


async def _render_result(
    target: Message,
    session: AsyncSession,
    attempt,
    *,
    edit: bool,
    expanded: int = 0,
    user_id: int | None = None,
    wipe_panel: bool = False,
    state: FSMContext | None = None,
) -> None:
    topic = await repos.get_topic(session, attempt.topic_id)
    title = topic.title if topic else "тема"
    answers = await repos.get_attempt_answers(session, attempt.id)
    text = _result_text(title, attempt)
    if expanded:
        row = next((item for item in answers if item.sort_order == expanded), None)
        if row is not None:
            text += await _expanded_section(session, row)
            if len(text) > RESULT_LIMIT:
                text = text[: RESULT_LIMIT - 1] + "…"
    uid = user_id or (target.chat.id if target else attempt.user_id)
    kb = exam_result_reply_keyboard(answers, admin=is_admin(uid))
    if wipe_panel and state is not None:
        await _forget_exam_panel(target.bot, target.chat.id, state, attempt)
    if state is None:
        if edit:
            await _safe_edit(target, text, None)
        else:
            await target.answer(text, reply_markup=kb)
        return
    if edit:
        data = await state.get_data()
        mid = data.get("result_message_id")
        if mid:
            try:
                await target.bot.edit_message_text(
                    text, chat_id=target.chat.id, message_id=int(mid)
                )
                return
            except TelegramBadRequest:
                pass
    await nav.goto(
        state, {"s": "exam_result", "a": attempt.id, "t": attempt.topic_id}
    )
    sent = await _present(target, state, text, kb, edit=False)
    await state.update_data(
        result_attempt_id=attempt.id, result_message_id=sent.message_id
    )


async def _show_history(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    topic_id: int,
    *,
    edit: bool = False,
) -> None:
    topic = await repos.get_topic(session, topic_id)
    if topic is None:
        await _present(target, state, "Тема не найдена.", edit=edit)
        return
    attempts = await repos.list_topic_attempts(session, user.id, topic.id)
    await nav.goto(state, {"s": "history", "t": topic.id})
    if not attempts:
        await _present(
            target,
            state,
            f'Тема «{topic.title}»\nИстории сдач пока нет.',
            edit=edit,
        )
        return
    lines = [f'Тема «{topic.title}»']
    for index, attempt in enumerate(attempts, start=1):
        solved = attempt.correct_count if attempt.correct_count is not None else 0
        total = attempt.total or 0
        lines.append(
            f"{index}. {format_dt(attempt.started_at)} Решено: {solved}/{total}"
        )
    await _present(target, state, "\n".join(lines), edit=edit)


async def _show_details(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    attempt_id: int,
    *,
    edit: bool = False,
) -> None:
    attempt = await repos.get_attempt(session, attempt_id)
    if attempt is None:
        await _present(target, state, "Результаты не найдены.", edit=edit)
        return
    await nav.goto(
        state, {"s": "exam_result", "a": attempt.id, "t": attempt.topic_id}
    )
    await _render_result(target, session, attempt, edit=edit, state=state)


async def _show_exam_info(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    topic_id: int,
    *,
    edit: bool = False,
) -> None:
    topic = await repos.get_topic(session, topic_id)
    if topic is None:
        await target.answer("Тема не найдена.")
        return
    now = _now()
    attempt = await repos.get_active_attempt(session, user.id, topic_id)
    attempt = await _maybe_expire(session, attempt, now)
    if attempt and attempt.status == "in_progress":
        stack = await nav.get_stack(state)
        if stack and stack[-1].get("s") == "exam_info":
            previous = await nav.replace_top(
                state, {"s": "exam_work", "t": topic_id}
            )
            if previous:
                await delete_quietly(
                    target.bot, target.chat.id, previous.get("ids") or []
                )
        else:
            await nav.goto(state, {"s": "exam_work", "t": topic_id})
        await _show_exam_work(
            target, state, session, topic, attempt, edit=False
        )
        return
    if attempt and attempt.status != "in_progress":
        await _render_result(
            target,
            session,
            attempt,
            edit=False,
            wipe_panel=True,
            user_id=user.id,
            state=state,
        )
        return
    await nav.goto(state, {"s": "exam_info", "t": topic_id})
    await state.update_data(topic_id=topic.id)
    problems = list(await repos.list_problems(session, topic.id, "assessment"))
    total = assessment_size(topic.assessment_required, len(problems))
    if total <= 0:
        text = f"В теме «{topic.title}» пока нет заданий для проверочной."
        markup = None
    else:
        text = exam_rules_text(topic.title, total, ASSESSMENT_HOURS)
        markup = exam_start_reply_keyboard(admin=is_admin(user.id))
    await _present(target, state, text, markup, edit=False)


async def _show_exam_work(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    topic,
    attempt,
    *,
    edit: bool = False,
) -> None:
    answers = await repos.get_attempt_answers(session, attempt.id)
    text = (
        f"{exam_rules_text(topic.title, attempt.total, ASSESSMENT_HOURS)}\n\n"
        f"Начата: {format_dt(attempt.started_at)}\n"
        f"Сдать до: {format_dt(attempt.deadline_at)}\n"
        "Выбери задание в меню внизу."
    )
    data = await state.get_data()
    panel_ids = [item for item in dict.fromkeys(data.get("exam_panel_ids") or []) if item]
    if panel_ids:
        await _wipe_exam_question(target.bot, target.chat.id, state)
        await state.set_state(Learn.exam_work)
        await state.update_data(exam_attempt_id=attempt.id, exam_topic_id=topic.id)
        await nav.goto(state, {"s": "exam_work", "t": topic.id})
        await nav.attach_ids(state, panel_ids)
        return
    await _wipe_exam_question(target.bot, target.chat.id, state)
    if edit:
        try:
            await target.delete()
        except TelegramBadRequest:
            pass
    await nav.goto(state, {"s": "exam_work", "t": topic.id})
    sent = await target.answer(text, reply_markup=_exam_kb(attempt.user_id, answers))
    attempt.panel_message_id = sent.message_id
    await remember_exam_panel(state, sent.message_id)
    await nav.attach_ids(state, [sent.message_id])
    await nav.adopt_reply_kb(target.bot, target.chat.id, state, sent.message_id)
    await state.set_state(Learn.exam_work)
    await state.update_data(exam_attempt_id=attempt.id, exam_topic_id=topic.id)


async def _refresh_exam_keyboard(
    target: Message, state: FSMContext, user_id: int, answers
) -> None:
    sent = await target.answer(
        "Ответ сохранён.",
        reply_markup=_exam_kb(user_id, answers),
    )
    await nav.adopt_reply_kb(target.bot, target.chat.id, state, sent.message_id)


@router.message(F.text == BTN_CONTINUE)
@router.message(Command("learn"))
async def btn_learn(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user, error = await _require_student(session, message.from_user, message)
    if error == "denied":
        return
    await nav.wipe_ui(
        message.bot, message.chat.id, state, extra=[message.message_id]
    )
    await state.set_state(None)
    if error:
        await message.answer(
            "Сначала выбери предмет и класс в «Настройках» или через /start.",
            reply_markup=menu_for(user.id),
        )
        return
    await show_learn_list(message, state, session, user)


@router.message(F.text == BTN_PROGRESS)
@router.message(Command("progress"))
async def btn_progress(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user, error = await _require_student(session, message.from_user, message)
    if error == "denied":
        return
    await nav.wipe_ui(
        message.bot, message.chat.id, state, extra=[message.message_id]
    )
    await state.set_state(None)
    if error:
        await message.answer(
            "Сначала выбери предмет и класс в «Настройках» или через /start.",
            reply_markup=menu_for(user.id),
        )
        return
    await show_progress_list(message, state, session, user)


@router.message(F.text == BTN_SETTINGS)
@router.message(Command("settings"))
async def btn_settings(message: Message, state: FSMContext) -> None:
    await nav.wipe_ui(
        message.bot, message.chat.id, state, extra=[message.message_id]
    )
    await state.set_state(None)
    await show_settings(message, state)


@router.message(Learn.pick_topic, F.text.regexp(r"^Начать с\s+\d+$"))
async def start_from_button(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user, error = await _require_student(session, message.from_user, message)
    if error == "denied":
        return
    if error:
        await message.answer(
            "Сначала выбери предмет и класс в «Настройках» или через /start.",
            reply_markup=menu_for(user.id),
        )
        return
    data = await state.get_data()
    topic_id = data.get("start_topic_id")
    topic = await repos.get_topic(session, int(topic_id)) if topic_id else None
    if topic is None:
        number = parse_start_from_button(message.text)
        if number:
            topic = await repos.get_topic_by_number(
                session, user.track_id, user.grade, number
            )
    if topic is None:
        await message.answer("Тема не найдена.")
        return
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    await _open_theory(message, state, session, user, topic.id)


@router.message(
    Learn.pick_topic,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(NAV_BUTTONS),
)
async def pick_topic_by_number(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user, error = await _require_student(session, message.from_user, message)
    if error == "denied":
        return
    if error:
        await message.answer(
            "Сначала выбери предмет и класс в «Настройках» или через /start.",
            reply_markup=menu_for(user.id),
        )
        return
    raw = (message.text or "").strip()
    history_match = re.fullmatch(r"(?:и|история)\s*(\d+)", raw, flags=re.IGNORECASE)
    if history_match:
        number = int(history_match.group(1))
        topic = await repos.get_topic_by_number(
            session, user.track_id, user.grade, number
        )
        if topic is None:
            await message.answer(f"Темы с номером {number} нет в этом классе.")
            return
        await delete_quietly(message.bot, message.chat.id, [message.message_id])
        await _show_history(message, state, session, user, topic.id, edit=False)
        return
    if not raw.isdigit():
        await message.answer("Напиши номер темы цифрой, например 2.")
        return
    number = int(raw)
    topic = await repos.get_topic_by_number(
        session, user.track_id, user.grade, number
    )
    if topic is None:
        await message.answer(f"Темы с номером {number} нет в этом классе.")
        return
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    await _open_theory(message, state, session, user, topic.id)


async def _apply_screen_state(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    screen: dict,
    *,
    force_menu: bool = False,
) -> None:
    kind = screen.get("s")
    if kind == "learn":
        await state.set_state(Learn.pick_topic)
        await state.update_data(pick_source="learn")
    elif kind == "progress":
        await state.set_state(Learn.pick_topic)
        await state.update_data(pick_source="progress")
    elif kind == "settings":
        await state.set_state(None)
    elif kind == "theory":
        await state.set_state(Learn.waiting_answer)
        await state.update_data(
            topic_id=screen.get("t"),
            stage="theory",
            current_problem_id=None,
        )
    elif kind == "training":
        await state.set_state(Learn.waiting_answer)
        await state.update_data(topic_id=screen.get("t"), stage="training")
    elif kind == "exam_info":
        await state.update_data(topic_id=screen.get("t"))
    elif kind == "exam_work":
        await state.set_state(Learn.exam_work)
        await state.update_data(exam_topic_id=screen.get("t"))
    elif kind == "exam_result":
        await state.set_state(None)
    elif kind == "history":
        await state.set_state(Learn.pick_topic)
    elif kind == "subjects":
        await state.set_state(Onboarding.subject)
    elif kind == "grades":
        await state.set_state(Onboarding.grade)
    elif kind == "stub":
        await state.set_state(None)
    else:
        await state.set_state(None)
    await _restore_section_reply(
        target, state, user.id, screen, force=force_menu
    )


async def _discard_screen(
    target: Message, state: FSMContext, session: AsyncSession, screen: dict
) -> None:
    kind = screen.get("s")
    ids = list(screen.get("ids") or [])
    if kind == "exam_work":
        await _wipe_exam_question(target.bot, target.chat.id, state)
        data = await state.get_data()
        ids.extend(data.get("exam_question_ids") or [])
        ids.extend(data.get("exam_panel_ids") or [])
        attempt_id = data.get("exam_attempt_id")
        attempt = await repos.get_attempt(session, int(attempt_id)) if attempt_id else None
        await _forget_exam_panel(target.bot, target.chat.id, state, attempt)
    elif kind == "training":
        data = await state.get_data()
        ids.extend(data.get("ephemeral_ids") or [])
        await state.update_data(
            ephemeral_ids=[], current_problem_message_id=None
        )
    elif kind == "theory":
        data = await state.get_data()
        ids.extend(data.get("theory_message_ids") or [])
        if data.get("theory_message_id"):
            ids.append(int(data["theory_message_id"]))
        await state.update_data(theory_message_ids=[], theory_message_id=None)
    await delete_quietly(target.bot, target.chat.id, ids)
    await nav.forget_reply_kb_if_deleted(state, ids)


async def _navigate_home(target: Message, state: FSMContext, user_id: int) -> None:
    extra = []
    if target.from_user and not target.from_user.is_bot:
        extra.append(target.message_id)
    await nav.wipe_ui(target.bot, target.chat.id, state, extra=extra)
    await state.set_state(None)
    sent = await target.answer(nav.HOME_TEXT, reply_markup=menu_for(user_id))
    await nav.reset_stack(state, {"s": "home"})
    await nav.attach_ids(state, [sent.message_id])
    await nav.adopt_reply_kb(target.bot, target.chat.id, state, sent.message_id)


async def _navigate_back(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
) -> None:
    current_state = await state.get_state()
    if current_state and str(current_state).endswith(":exam_answer"):
        data = await state.get_data()
        if data.get("exam_question_ids"):
            await _wipe_exam_question(target.bot, target.chat.id, state)
            await state.set_state(Learn.exam_work)
            await state.update_data(exam_problem_id=None)
            return
    stack = await nav.get_stack(state)
    if len(stack) <= 1:
        await _navigate_home(target, state, user.id)
        return
    current = await nav.pop_screen(state)
    if current:
        await _discard_screen(target, state, session, current)
    remaining = await nav.get_stack(state)
    if not remaining:
        await _navigate_home(target, state, user.id)
        return
    data = await state.get_data()
    need_kb = data.get("reply_kb_id") is None
    await _apply_screen_state(
        target, state, session, user, remaining[-1], force_menu=need_kb
    )


@router.callback_query(MenuCB.filter(F.a == "hm"))
async def go_home(callback: CallbackQuery, state: FSMContext) -> None:
    await _navigate_home(callback.message, state, callback.from_user.id)
    await callback.answer()


@router.message(F.text == BTN_HOME)
async def home_text(message: Message, state: FSMContext) -> None:
    await _navigate_home(message, state, message.from_user.id)


@router.callback_query(MenuCB.filter(F.a == "bk"))
async def go_back(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    user = await ensure_user(session, callback.from_user)
    await _navigate_back(callback.message, state, session, user)
    await callback.answer()


@router.message(F.text == BTN_BACK)
async def back_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    user = await ensure_user(session, message.from_user)
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    await _navigate_back(message, state, session, user)


@router.callback_query(MenuCB.filter(F.a == "th"))
async def open_theory(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user, error = await _require_student(session, callback.from_user, callback.message)
    if error == "denied":
        await callback.answer("Нет доступа", show_alert=True)
        return
    if error:
        await callback.answer("Сначала выбери предмет и класс", show_alert=True)
        return
    await _open_theory(callback.message, state, session, user, callback_data.t)
    await callback.answer()


@router.callback_query(MenuCB.filter(F.a == "st"))
async def start_from_list(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user, error = await _require_student(session, callback.from_user, callback.message)
    if error == "denied":
        await callback.answer("Нет доступа", show_alert=True)
        return
    if error:
        await callback.answer("Сначала выбери предмет и класс", show_alert=True)
        return
    await _open_theory(callback.message, state, session, user, callback_data.t)
    await callback.answer()


@router.callback_query(MenuCB.filter(F.a == "ex"))
async def exam_info(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user, error = await _require_student(session, callback.from_user, callback.message)
    if error == "denied":
        await callback.answer("Нет доступа", show_alert=True)
        return
    if error:
        await callback.answer("Сначала выбери предмет и класс", show_alert=True)
        return
    await _show_exam_info(
        callback.message, state, session, user, callback_data.t, edit=False
    )
    await callback.answer()


async def _begin_exam(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    topic,
) -> str | None:
    now = _now()
    attempt = await repos.get_active_attempt(session, user.id, topic.id)
    attempt = await _maybe_expire(session, attempt, now)
    if attempt is None or attempt.status != "in_progress":
        previous = await repos.list_topic_attempts(session, user.id, topic.id)
        avoid = repos.parse_id_list(previous[-1].problem_ids) if previous else []
        chosen = await pick_assessment_queue(session, topic, avoid_ids=avoid)
        if not chosen:
            return "Нет заданий для проверочной"
        attempt = await repos.create_assessment_attempt(
            session,
            user_id=user.id,
            topic_id=topic.id,
            problem_ids=chosen,
            started_at=now,
            deadline_at=now + timedelta(hours=ASSESSMENT_HOURS),
        )
        progress = await repos.get_or_create_progress(session, user.id, topic.id)
        progress.theory_done = True
        if progress.mastery == "not_started":
            progress.mastery = "learning"
    previous = await nav.replace_top(state, {"s": "exam_work", "t": topic.id})
    if previous:
        await delete_quietly(
            target.bot, target.chat.id, previous.get("ids") or []
        )
    await _show_exam_work(target, state, session, topic, attempt, edit=False)
    return None


@router.callback_query(MenuCB.filter(F.a == "go"))
async def exam_start(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user, error = await _require_student(session, callback.from_user, callback.message)
    if error == "denied":
        await callback.answer("Нет доступа", show_alert=True)
        return
    if error:
        await callback.answer("Сначала выбери предмет и класс", show_alert=True)
        return
    topic = await repos.get_topic(session, callback_data.t)
    if topic is None:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    fail = await _begin_exam(callback.message, state, session, user, topic)
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.message(F.text == BTN_EXAM_START)
async def exam_start_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    stack = await nav.get_stack(state)
    if stack and stack[-1].get("s") == "exam_info":
        topic_id = stack[-1].get("t") or topic_id
    if not topic_id:
        return
    user, error = await _require_student(session, message.from_user, message)
    if error:
        return
    topic = await repos.get_topic(session, int(topic_id))
    if topic is None:
        await message.answer("Тема не найдена.")
        return
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _begin_exam(message, state, session, user, topic)
    if fail:
        await message.answer(fail)


async def _open_exam_question(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    topic_id: int,
    sort_order: int,
    *,
    pick_message: Message | None = None,
) -> str | None:
    now = _now()
    attempt = await repos.get_active_attempt(session, user.id, topic_id)
    attempt = await _maybe_expire(session, attempt, now)
    if attempt is None or attempt.status != "in_progress":
        if attempt is not None:
            await _render_result(
                target,
                session,
                attempt,
                edit=False,
                wipe_panel=True,
                user_id=user.id,
                state=state,
            )
            return "expired" if attempt.status == "expired" else "done"
        return "gone"
    answers = await repos.get_attempt_answers(session, attempt.id)
    row = next((item for item in answers if item.sort_order == sort_order), None)
    problem = await repos.get_problem(session, row.problem_id) if row else None
    if row is None or problem is None:
        return "missing"
    if pick_message is not None:
        await delete_quietly(target.bot, target.chat.id, [pick_message.message_id])
    await _wipe_exam_question(target.bot, target.chat.id, state)
    await state.set_state(Learn.exam_answer)
    await state.update_data(
        exam_attempt_id=attempt.id,
        exam_topic_id=attempt.topic_id,
        exam_problem_id=problem.id,
        exam_sort=row.sort_order,
    )
    current = (row.submitted or "").strip()
    extra = f"\nТекущий ответ: <code>{current}</code>" if current else ""
    header = (
        f"<b>Задание {row.sort_order} из {attempt.total}</b>\n"
        f"Напиши ответ сообщением.{extra}"
    )
    ids = await send_rich(
        target,
        problem.prompt,
        header=header,
    )
    await state.update_data(exam_question_ids=ids)
    await nav.track_ui(state, ids)
    return None


@router.callback_query(MenuCB.filter(F.a == "qi"))
async def exam_question(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await ensure_user(session, callback.from_user)
    error = await _open_exam_question(
        callback.message,
        state,
        session,
        user,
        callback_data.t,
        callback_data.i,
    )
    if error == "missing":
        await callback.answer("Задание не найдено", show_alert=True)
        return
    if error == "gone":
        await callback.answer("Проверочная уже завершена", show_alert=True)
        return
    if error:
        await callback.answer(
            "Время вышло" if error == "expired" else "Работа завершена"
        )
        return
    await callback.answer()


@router.message(
    StateFilter(Learn.exam_work, Learn.exam_answer),
    F.text.regexp(r"^\d+\s*[·•.]\s*(Нет ответа|ответ отправлен)$"),
)
async def exam_pick_task(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    number = parse_exam_task_button(message.text)
    data = await state.get_data()
    topic_id = data.get("exam_topic_id")
    if number is None or not topic_id:
        return
    user = await ensure_user(session, message.from_user)
    error = await _open_exam_question(
        message,
        state,
        session,
        user,
        int(topic_id),
        number,
        pick_message=message,
    )
    if error == "missing":
        await message.answer("Задание не найдено.")
    elif error == "gone":
        await message.answer("Проверочная уже завершена.", reply_markup=menu_for(user.id))


@router.message(
    Learn.exam_answer,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(NAV_BUTTONS),
)
async def exam_answer(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    if parse_exam_task_button(message.text) is not None:
        return
    data = await state.get_data()
    attempt_id = data.get("exam_attempt_id")
    problem_id = data.get("exam_problem_id")
    if not attempt_id or not problem_id:
        return
    attempt = await repos.get_attempt(session, int(attempt_id))
    now = _now()
    attempt = await _maybe_expire(session, attempt, now)
    if attempt is None or attempt.status != "in_progress":
        await _wipe_exam_question(message.bot, message.chat.id, state)
        if attempt is not None:
            await _render_result(
                message,
                session,
                attempt,
                edit=False,
                wipe_panel=True,
                user_id=message.from_user.id,
                state=state,
            )
        else:
            await message.answer(
                "Проверочная уже завершена.",
                reply_markup=menu_for(message.from_user.id),
            )
        await state.set_state(None)
        return
    if attempt.user_id != message.from_user.id:
        return
    await repos.save_attempt_answer(
        session, attempt.id, int(problem_id), (message.text or "").strip()
    )
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    await _wipe_exam_question(message.bot, message.chat.id, state)
    answers = await repos.get_attempt_answers(session, attempt.id)
    await _refresh_exam_keyboard(message, state, message.from_user.id, answers)
    await state.set_state(Learn.exam_work)
    await state.update_data(exam_problem_id=None)


async def _finish_exam_attempt(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    topic_id: int,
    *,
    edit: bool,
) -> bool:
    attempt = await repos.get_active_attempt(session, user.id, topic_id)
    if attempt is None:
        return False
    now = _now()
    status = (
        "expired"
        if attempt.deadline_at and now >= attempt.deadline_at
        else "completed"
    )
    await _complete_attempt(session, attempt, now=now, status=status)
    await _wipe_exam_question(target.bot, target.chat.id, state)
    stack = await nav.get_stack(state)
    if stack and stack[-1].get("s") in {"exam_work", "exam_info"}:
        await nav.pop_screen(state)
    await state.set_state(None)
    await state.update_data(result_expanded=0)
    await _render_result(
        target,
        session,
        attempt,
        edit=False,
        wipe_panel=True,
        user_id=user.id,
        state=state,
    )
    return True


@router.callback_query(MenuCB.filter(F.a == "fi"))
async def exam_finish(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await ensure_user(session, callback.from_user)
    ok = await _finish_exam_attempt(
        callback.message,
        state,
        session,
        user,
        callback_data.t,
        edit=True,
    )
    await callback.answer("Работа сдана" if ok else "Нет активной работы", show_alert=not ok)


@router.message(F.text == BTN_EXAM_FINISH)
async def exam_finish_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    topic_id = data.get("exam_topic_id")
    if not topic_id:
        return
    user = await ensure_user(session, message.from_user)
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    ok = await _finish_exam_attempt(
        message, state, session, user, int(topic_id), edit=False
    )
    if not ok:
        await message.answer("Нет активной работы.", reply_markup=menu_for(user.id))


async def _toggle_result_item(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user,
    sort_order: int,
    *,
    pick_message: Message | None = None,
) -> None:
    data = await state.get_data()
    attempt_id = data.get("result_attempt_id")
    if not attempt_id:
        stack = await nav.get_stack(state)
        if stack and stack[-1].get("s") == "exam_result":
            attempt_id = stack[-1].get("a")
    if not attempt_id:
        return
    attempt = await repos.get_attempt(session, int(attempt_id))
    if attempt is None or attempt.user_id != user.id:
        return
    if pick_message is not None:
        await delete_quietly(target.bot, target.chat.id, [pick_message.message_id])
    current = int(data.get("result_expanded") or 0)
    expanded = 0 if current == sort_order else sort_order
    await state.update_data(result_expanded=expanded)
    await _render_result(
        target,
        session,
        attempt,
        edit=True,
        expanded=expanded,
        state=state,
        user_id=user.id,
    )


async def _open_class_picker(
    target: Message, state: FSMContext, session: AsyncSession
) -> str | None:
    subjects = await repos.list_subjects(session)
    await state.set_state(Onboarding.subject)
    await state.update_data(from_settings=True)
    await nav.goto(state, {"s": "subjects"})
    if not subjects:
        return "Предметы ещё не добавлены"
    await _present(
        target,
        state,
        "Выбери предмет. Прогресс по другим предметам сохранится.",
        subject_keyboard(subjects),
        edit=False,
    )
    return None


async def _open_settings_stub(
    target: Message, state: FSMContext, stub_id: int
) -> None:
    await nav.goto(state, {"s": "stub", "i": stub_id})
    await _present(
        target,
        state,
        STUBS.get(stub_id, "Раздел в разработке."),
        edit=False,
    )


@router.callback_query(MenuCB.filter(F.a == "dt"))
async def exam_details(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    attempt = await repos.get_attempt(session, callback_data.t)
    if attempt is None or attempt.user_id != callback.from_user.id:
        await callback.answer("Результаты не найдены", show_alert=True)
        return
    await state.update_data(result_expanded=0)
    await _show_details(callback.message, state, session, attempt.id, edit=True)
    await callback.answer()


@router.callback_query(MenuCB.filter(F.a == "dq"))
async def exam_detail_item(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    attempt = await repos.get_attempt(session, callback_data.t)
    if attempt is None or attempt.user_id != callback.from_user.id:
        await callback.answer("Нет доступа", show_alert=True)
        return
    data = await state.get_data()
    current = int(data.get("result_expanded") or 0)
    expanded = 0 if current == callback_data.i else callback_data.i
    await state.update_data(result_expanded=expanded)
    await _render_result(
        callback.message,
        session,
        attempt,
        edit=True,
        expanded=expanded,
        state=state,
        user_id=callback.from_user.id,
    )
    await callback.answer()


@router.callback_query(MenuCB.filter(F.a == "hs"))
async def topic_history(
    callback: CallbackQuery,
    callback_data: MenuCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await ensure_user(session, callback.from_user)
    topic = await repos.get_topic(session, callback_data.t)
    if topic is None:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    await _show_history(callback.message, state, session, user, topic.id, edit=False)
    await callback.answer()


@router.callback_query(MenuCB.filter(F.a == "sc"))
async def settings_class(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    fail = await _open_class_picker(callback.message, state, session)
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.callback_query(MenuCB.filter(F.a == "sb"))
async def settings_stub(
    callback: CallbackQuery, callback_data: MenuCB, state: FSMContext
) -> None:
    await _open_settings_stub(callback.message, state, callback_data.i)
    await callback.answer()


@router.message(F.text == BTN_CHANGE_CLASS)
async def settings_class_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _open_class_picker(message, state, session)
    if fail:
        await message.answer(fail)


@router.message(F.text.in_({BTN_SUB, BTN_APPEAL, BTN_SCHEDULE}))
async def settings_stub_text(message: Message, state: FSMContext) -> None:
    stub_id = {BTN_SUB: 1, BTN_APPEAL: 2, BTN_SCHEDULE: 3}[message.text]
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    await _open_settings_stub(message, state, stub_id)


@router.message(F.text.regexp(r"^\d+\s*[·•.]\s*(верно|неверно|нет ответа)$"))
async def exam_result_pick(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    number = parse_exam_result_button(message.text)
    if number is None:
        return
    user = await ensure_user(session, message.from_user)
    await _toggle_result_item(
        message, state, session, user, number, pick_message=message
    )
