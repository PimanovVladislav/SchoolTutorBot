from types import SimpleNamespace

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.config import TRAINING_REPEAT_DAYS, WRONG_ATTEMPTS_BEFORE_HELP
from tutor_bot.db import repos
from tutor_bot.db.models import Problem, Topic, User
from tutor_bot.keyboards import (
    BTN_LEVEL_DOWN,
    BTN_LEVEL_UP,
    BTN_THEORY_MORE,
    BTN_TO_EXAM,
    BTN_TO_TRAINING,
    BTN_TRAIN_MORE,
    DIFFICULTY_LABELS,
    LearnCB,
    TopicCB,
    answer_keyboard,
    menu_for,
    theory_reply_keyboard,
    training_reply_keyboard,
    NAV_BUTTONS,
)
from tutor_bot.services.access import is_admin
from tutor_bot.services.chat import (
    delete_quietly,
    track_ephemeral,
    track_theory,
    wipe_ephemeral,
    wipe_lesson,
)
from tutor_bot.services.learning import (
    apply_assessment_score,
    apply_reinforcement_result,
    build_start_queue,
)
from tutor_bot.services import nav
from tutor_bot.services.richtext import send_rich
from tutor_bot.services.scoring import MASTERY_LABELS, mastery_from_score
from tutor_bot.states import Learn

router = Router()

KIND_TITLES = {
    "reinforcement": "Закрепление",
    "training": "Тренировка",
    "assessment": "Проверочная",
}


def _difficulty_title(level: int) -> str:
    label = DIFFICULTY_LABELS.get(level, str(level))
    return f"уровень {level} ({label})"


def _problem_text(stage: str, problem: Problem, *, extra: str = "") -> str:
    title = KIND_TITLES.get(stage, "Задание")
    if stage == "training":
        title = f"{title} · {_difficulty_title(problem.difficulty)}"
    header = f"<b>{title}</b>\nЗадание #{problem.id}"
    if extra:
        header += f" · {extra}"
    return header


async def start_topic(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    topic: Topic,
) -> None:
    await show_topic_theory(message, state, session, user, topic)


async def show_topic_theory(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    topic: Topic,
) -> None:
    await wipe_lesson(message.bot, message.chat.id, state)
    await repos.set_current_topic(session, user.id, topic.id)
    progress = await repos.get_or_create_progress(session, user.id, topic.id)
    progress.theory_done = True
    if progress.mastery == "not_started":
        progress.mastery = "learning"
    learning = await repos.create_session(session, user.id, topic.id, "theory")
    await state.set_state(Learn.waiting_answer)
    await state.update_data(
        session_id=learning.id,
        topic_id=topic.id,
        stage="theory",
        theory_edition=1,
        current_problem_id=None,
    )
    await _send_theory(message, state, session, topic)


async def _topic_theories(session: AsyncSession, topic: Topic) -> list:
    rows = list(await repos.list_topic_theories(session, topic.id))
    if rows:
        return rows
    body = topic.theory or topic.summary or topic.title
    return [
        SimpleNamespace(
            edition=1,
            edition_count=1,
            body=body,
            kind=topic.theory_kind or "text",
            image_path=topic.theory_image_path,
        )
    ]


def _has_more_edition(item) -> bool:
    return int(item.edition) < int(item.edition_count or item.edition)


async def _clear_theory_markup(bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    message_id = data.get("theory_message_id")
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None
        )
    except TelegramBadRequest:
        pass


async def _send_theory_edition(
    target: Message,
    state: FSMContext,
    topic: Topic,
    item,
) -> None:
    markup = theory_reply_keyboard(
        can_more=_has_more_edition(item),
        admin=is_admin(target.chat.id),
    )
    header = f"<b>{topic.title}</b>"
    total = int(item.edition_count or 1)
    if total > 1:
        header += f"\nРедакция {item.edition} из {total}"
    kind = (item.kind or "text").lower()
    image_path = getattr(item, "image_path", None)
    extra_photo = image_path if kind == "photo" and image_path else None
    body = item.body or topic.summary or topic.title
    ids = await send_rich(
        target,
        body,
        header=header,
        reply_markup=markup,
        extra_photo=extra_photo,
    )
    for message_id in ids:
        await track_theory(state, message_id)
    await nav.attach_ids(state, ids)
    if ids:
        await nav.adopt_reply_kb(target.bot, target.chat.id, state, ids[-1])


async def _send_theory(
    message: Message, state: FSMContext, session: AsyncSession, topic: Topic
) -> None:
    progress = await repos.get_or_create_progress(session, message.chat.id, topic.id)
    progress.theory_done = True
    theories = await _topic_theories(session, topic)
    first = theories[0]
    await _send_theory_edition(message, state, topic, first)
    await state.update_data(stage="theory", theory_edition=int(first.edition))


async def _send_current_problem(
    target: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    queue: list[int] = data.get("queue") or []
    index = int(data.get("index") or 0)
    stage = data.get("stage")
    if index >= len(queue):
        await _finish_stage(target, state, session, stage)
        return
    problem = await repos.get_problem(session, queue[index])
    if problem is None:
        await state.update_data(index=index + 1)
        await _send_current_problem(target, state, session)
        return
    extra = ""
    if stage == "assessment":
        extra = f"{index + 1} из {len(queue)}"
    await _present_problem(target, state, session, problem, stage, extra=extra)


async def _present_problem(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    problem: Problem,
    stage: str,
    *,
    extra: str = "",
) -> None:
    await wipe_ephemeral(target.bot, target.chat.id, state)
    header = _problem_text(stage, problem, extra=extra)
    hints = await repos.list_hint_bodies(session, problem)
    ids = await send_rich(
        target,
        problem.prompt,
        header=header,
        reply_markup=answer_keyboard(
            show_help=False,
            can_skip=stage == "training",
            show_hint=bool(hints),
        ),
    )
    for message_id in ids:
        await track_ephemeral(state, message_id)
    await nav.attach_ids(state, ids)
    used = list((await state.get_data()).get("used_problem_ids") or [])
    if problem.id not in used:
        used.append(problem.id)
    await state.update_data(
        current_problem_id=problem.id,
        attempt_count=0,
        used_help=False,
        hint_used=False,
        hint_edition=0,
        solution_edition=0,
        problem_base_text=header,
        used_problem_ids=used,
        current_difficulty=problem.difficulty,
    )


async def _send_training_problem(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    *,
    difficulty: int,
    user_id: int,
    exclude_current: bool = True,
    exclude_session_used: bool = True,
) -> bool:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if not topic_id:
        return False
    exclude: list[int] = []
    if exclude_session_used:
        exclude.extend(data.get("used_problem_ids") or [])
    current = data.get("current_problem_id")
    if exclude_current and current:
        exclude.append(int(current))
    problem = await repos.pick_training_problem(
        session,
        user_id,
        topic_id,
        difficulty,
        exclude_ids=exclude,
        cooldown_days=TRAINING_REPEAT_DAYS,
    )
    if problem is None:
        return False
    await _present_problem(target, state, session, problem, "training")
    return True


async def _next_difficulty(
    session: AsyncSession, topic_id: int, current: int
) -> int | None:
    levels = await repos.list_difficulties(session, topic_id, "training")
    higher = [level for level in levels if level > current]
    return higher[0] if higher else None


async def _prev_difficulty(
    session: AsyncSession, topic_id: int, current: int
) -> int | None:
    levels = await repos.list_difficulties(session, topic_id, "training")
    lower = [level for level in levels if level < current]
    return lower[-1] if lower else None


async def _finish_stage(
    target: Message, state: FSMContext, session: AsyncSession, stage: str
) -> None:
    data = await state.get_data()
    topic = await repos.get_topic(session, data["topic_id"])
    session_id = data["session_id"]
    if topic is None:
        await wipe_lesson(target.bot, target.chat.id, state)
        await state.clear()
        await target.bot.send_message(
            target.chat.id,
            "Тема не найдена.",
            reply_markup=menu_for(target.chat.id),
        )
        return
    if stage == "reinforcement":
        await wipe_ephemeral(target.bot, target.chat.id, state)
        await repos.set_session_stage(session, session_id, "theory")
        await state.update_data(stage="theory", queue=[], index=0)
        await _send_theory(target, state, session, topic)
        return
    if stage == "assessment":
        queue = list(data.get("queue") or [])
        problems = await repos.get_problems_by_ids(session, queue)
        attempts = await repos.list_session_attempts(session, session_id)
        score = await apply_assessment_score(
            session, target.chat.id, topic.id, problems, attempts
        )
        await repos.finish_session(session, session_id)
        await wipe_lesson(target.bot, target.chat.id, state)
        await state.clear()
        mastery = MASTERY_LABELS[mastery_from_score(score)]
        await target.bot.send_message(
            target.chat.id,
            f"<b>Проверочная закрыта</b>\n"
            f"Тема: {topic.title}\n"
            f"Оценка: {score:.0f}%\n"
            f"Уровень: {mastery}\n\n"
            "Посмотреть все темы — «Мой прогресс».",
            reply_markup=menu_for(target.chat.id),
        )
        return
    await target.bot.send_message(
        target.chat.id, "Этап завершён.", reply_markup=menu_for(target.chat.id)
    )


async def _edit_problem(
    target: Message, state: FSMContext, text: str, markup
) -> None:
    data = await state.get_data()
    message_id = data.get("current_problem_message_id")
    if not message_id:
        sent = await target.answer(text, reply_markup=markup)
        await track_ephemeral(state, sent.message_id)
        return
    try:
        await target.bot.edit_message_text(
            text,
            chat_id=target.chat.id,
            message_id=message_id,
            reply_markup=markup,
        )
    except TelegramBadRequest:
        sent = await target.answer(text, reply_markup=markup)
        await track_ephemeral(state, sent.message_id)


def _compose_problem_view(
    base: str,
    hints: list[str],
    solutions: list[str],
    *,
    wrong: bool = False,
) -> str:
    parts = [base]
    for index, text in enumerate(hints, start=1):
        parts.append(f"<b>Подсказка {index}</b>\n{text}")
    for index, text in enumerate(solutions, start=1):
        parts.append(f"<b>Разбор {index}</b>\n{text}")
    if wrong:
        parts.append("<i>Пока неверно. Попробуй ещё раз.</i>")
    return "\n\n".join(parts)


def _problem_keyboard(
    data: dict,
    *,
    hint_total: int,
    solution_total: int,
    show_report: bool = False,
):
    hint_shown = int(data.get("hint_edition") or 0)
    sol_shown = int(data.get("solution_edition") or 0)
    attempts = int(data.get("attempt_count") or 0)
    return answer_keyboard(
        show_help=solution_total > 0
        and sol_shown == 0
        and attempts >= WRONG_ATTEMPTS_BEFORE_HELP,
        show_help_more=sol_shown > 0 and sol_shown < solution_total,
        can_skip=data.get("stage") == "training",
        show_hint=hint_total > 0 and hint_shown == 0,
        show_hint_more=hint_shown > 0 and hint_shown < hint_total,
        show_report=show_report,
    )


async def _refresh_problem_keyboard(target: Message, state: FSMContext, markup) -> None:
    data = await state.get_data()
    message_id = data.get("current_problem_message_id")
    if not message_id:
        return
    try:
        await target.bot.edit_message_reply_markup(
            chat_id=target.chat.id,
            message_id=message_id,
            reply_markup=markup,
        )
    except TelegramBadRequest:
        pass


async def _advance_theory(target: Message, state: FSMContext, session: AsyncSession) -> str | None:
    data = await state.get_data()
    if data.get("stage") != "theory":
        return None
    topic = await repos.get_topic(session, data.get("topic_id") or 0)
    if topic is None:
        return "Тема не найдена"
    theories = await _topic_theories(session, topic)
    nxt = int(data.get("theory_edition") or 1) + 1
    item = next((row for row in theories if int(row.edition) == nxt), None)
    if item is None:
        return "Других объяснений нет"
    await _clear_theory_markup(target.bot, target.chat.id, state)
    await _send_theory_edition(target, state, topic, item)
    await state.update_data(theory_edition=int(item.edition))
    return None


async def _apply_training_keyboard(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user_id: int,
    difficulty: int | None = None,
    *,
    force: bool = False,
) -> None:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    current = int(difficulty or data.get("current_difficulty") or 1)
    nxt = await _next_difficulty(session, topic_id, current)
    prev = await _prev_difficulty(session, topic_id, current)
    await state.update_data(
        can_level_up=nxt is not None, can_level_down=prev is not None
    )
    await nav.apply_reply_keyboard(
        target,
        state,
        training_reply_keyboard(
            can_level_up=nxt is not None,
            can_level_down=prev is not None,
            admin=is_admin(user_id),
        ),
        force=force,
        caption="Тренировка. Выбери действие:",
    )


async def _start_training(
    target: Message, state: FSMContext, session: AsyncSession, user_id: int
) -> str | None:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if not topic_id:
        return "Сначала выбери тему"
    levels = await repos.list_difficulties(session, topic_id, "training")
    if not levels:
        return "В теме нет тренировочных задач"
    if not data.get("session_id"):
        learning = await repos.create_session(
            session, user_id, int(topic_id), "training"
        )
        await state.update_data(session_id=learning.id)
        data = await state.get_data()
    await repos.set_session_stage(session, data["session_id"], "training")
    await nav.goto(state, {"s": "training", "t": int(topic_id)})
    await state.update_data(
        stage="training",
        queue=[],
        index=0,
        used_problem_ids=[],
        current_difficulty=levels[0],
    )
    await _apply_training_keyboard(
        target, state, session, user_id, levels[0], force=True
    )
    ok = await _send_training_problem(
        target,
        state,
        session,
        difficulty=levels[0],
        user_id=user_id,
        exclude_current=False,
    )
    if not ok:
        return "Не удалось выбрать задачу"
    return None


async def _open_assessment(
    target: Message, state: FSMContext, session: AsyncSession, user
) -> str | None:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if not topic_id:
        return "Сначала выбери тему"
    topic = await repos.get_topic(session, topic_id)
    if topic is None:
        return "Тема не найдена"
    from tutor_bot.handlers.student import _show_exam_info

    await _show_exam_info(target, state, session, user, topic.id, edit=False)
    return None


async def _train_more(
    target: Message, state: FSMContext, session: AsyncSession, user_id: int
) -> str | None:
    data = await state.get_data()
    if data.get("stage") != "training":
        return None
    difficulty = int(data.get("current_difficulty") or 1)
    ok = await _send_training_problem(
        target, state, session, difficulty=difficulty, user_id=user_id
    )
    if not ok:
        return "Задач этого уровня пока нет"
    return None


async def _train_change_level(
    target: Message,
    state: FSMContext,
    session: AsyncSession,
    user_id: int,
    *,
    up: bool,
) -> str | None:
    data = await state.get_data()
    if data.get("stage") != "training":
        return None
    topic_id = data.get("topic_id")
    current = int(data.get("current_difficulty") or 1)
    nxt = (
        await _next_difficulty(session, topic_id, current)
        if up
        else await _prev_difficulty(session, topic_id, current)
    )
    if nxt is None:
        return "Это максимальный уровень" if up else "Это минимальный уровень"
    await state.update_data(current_difficulty=nxt, used_problem_ids=[])
    await _apply_training_keyboard(target, state, session, user_id, nxt, force=True)
    ok = await _send_training_problem(
        target,
        state,
        session,
        difficulty=nxt,
        user_id=user_id,
        exclude_current=False,
    )
    if not ok:
        return "На следующем уровне нет задач" if up else "На предыдущем уровне нет задач"
    return None


@router.callback_query(TopicCB.filter(F.action == "open"))
async def open_topic(
    callback: CallbackQuery,
    callback_data: TopicCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    from tutor_bot.handlers.common import ensure_user, require_access

    user = await ensure_user(session, callback.from_user)
    denied = await require_access(session, user)
    if denied:
        await callback.answer("Нет доступа", show_alert=True)
        await callback.message.answer(denied, reply_markup=menu_for(callback.from_user.id))
        return
    topic = await repos.get_topic(session, callback_data.topic_id)
    if topic is None:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    await show_topic_theory(callback.message, state, session, user, topic)
    await callback.answer()


@router.callback_query(LearnCB.filter(F.action == "theory_more"), Learn.waiting_answer)
async def theory_more(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    fail = await _advance_theory(callback.message, state, session)
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.message(Learn.waiting_answer, F.text == BTN_THEORY_MORE)
async def theory_more_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _advance_theory(message, state, session)
    if fail:
        await message.answer(fail)


@router.callback_query(LearnCB.filter(F.action == "training"), Learn.waiting_answer)
async def start_training(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    fail = await _start_training(
        callback.message, state, session, callback.from_user.id
    )
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.message(Learn.waiting_answer, F.text == BTN_TO_TRAINING)
async def start_training_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _start_training(message, state, session, message.from_user.id)
    if fail:
        await message.answer(fail)


@router.callback_query(LearnCB.filter(F.action == "assessment"), Learn.waiting_answer)
async def start_assessment(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    from tutor_bot.handlers.common import ensure_user

    user = await ensure_user(session, callback.from_user)
    fail = await _open_assessment(callback.message, state, session, user)
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.message(Learn.waiting_answer, F.text == BTN_TO_EXAM)
async def start_assessment_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    from tutor_bot.handlers.common import ensure_user

    user = await ensure_user(session, message.from_user)
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _open_assessment(message, state, session, user)
    if fail:
        await message.answer(fail)


@router.callback_query(LearnCB.filter(F.action == "more"), Learn.waiting_answer)
async def train_more(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    fail = await _train_more(callback.message, state, session, callback.from_user.id)
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.message(Learn.waiting_answer, F.text == BTN_TRAIN_MORE)
async def train_more_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _train_more(message, state, session, message.from_user.id)
    if fail:
        await message.answer(fail)


@router.callback_query(LearnCB.filter(F.action == "level_up"), Learn.waiting_answer)
async def train_level_up(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    fail = await _train_change_level(
        callback.message, state, session, callback.from_user.id, up=True
    )
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.message(Learn.waiting_answer, F.text == BTN_LEVEL_UP)
async def train_level_up_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _train_change_level(
        message, state, session, message.from_user.id, up=True
    )
    if fail:
        await message.answer(fail)


@router.callback_query(LearnCB.filter(F.action == "level_down"), Learn.waiting_answer)
async def train_level_down(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    fail = await _train_change_level(
        callback.message, state, session, callback.from_user.id, up=False
    )
    if fail:
        await callback.answer(fail, show_alert=True)
        return
    await callback.answer()


@router.message(Learn.waiting_answer, F.text == BTN_LEVEL_DOWN)
async def train_level_down_text(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    fail = await _train_change_level(
        message, state, session, message.from_user.id, up=False
    )
    if fail:
        await message.answer(fail)


@router.callback_query(LearnCB.filter(F.action == "hint"), Learn.waiting_answer)
async def show_hint(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    problem = await repos.get_problem(session, data.get("current_problem_id") or 0)
    if problem is None:
        await callback.answer("Задание не найдено", show_alert=True)
        return
    hints = await repos.list_hint_bodies(session, problem)
    solutions = await repos.list_solution_bodies(session, problem)
    shown = int(data.get("hint_edition") or 0) + 1
    if shown > len(hints):
        await callback.answer("Других подсказок нет", show_alert=True)
        return
    await state.update_data(hint_used=True, hint_edition=shown)
    data = await state.get_data()
    ids = await send_rich(
        callback.message,
        hints[shown - 1],
        header=f"<b>Подсказка {shown}</b>",
    )
    for message_id in ids:
        await track_ephemeral(state, message_id, control=False)
    await _refresh_problem_keyboard(
        callback.message,
        state,
        _problem_keyboard(
            data,
            hint_total=len(hints),
            solution_total=len(solutions),
            show_report=int(data.get("attempt_count") or 0) > 0,
        ),
    )
    await callback.answer()


@router.callback_query(LearnCB.filter(F.action == "help"), Learn.waiting_answer)
async def show_help(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    problem = await repos.get_problem(session, data.get("current_problem_id") or 0)
    if problem is None:
        await callback.answer("Задание не найдено", show_alert=True)
        return
    hints = await repos.list_hint_bodies(session, problem)
    solutions = await repos.list_solution_bodies(session, problem)
    shown = int(data.get("solution_edition") or 0) + 1
    if shown > len(solutions):
        await callback.answer("Других разборов нет", show_alert=True)
        return
    first_open = int(data.get("solution_edition") or 0) == 0
    await state.update_data(used_help=True, solution_edition=shown)
    if first_open:
        await repos.add_attempt(
            session,
            user_id=callback.from_user.id,
            session_id=data["session_id"],
            problem_id=problem.id,
            submitted="[help]",
            is_correct=False,
            used_help=True,
        )
        if data.get("stage") == "reinforcement":
            await apply_reinforcement_result(
                session, callback.from_user.id, problem, False
            )
    data = await state.get_data()
    hint_shown = int(data.get("hint_edition") or 0)
    ids = await send_rich(
        callback.message,
        solutions[shown - 1],
        header=f"<b>Разбор {shown}</b>",
    )
    for message_id in ids:
        await track_ephemeral(state, message_id, control=False)
    await _refresh_problem_keyboard(
        callback.message,
        state,
        _problem_keyboard(
            data,
            hint_total=len(hints),
            solution_total=len(solutions),
            show_report=int(data.get("attempt_count") or 0) > 0,
        ),
    )
    await callback.answer()
    if data.get("stage") == "assessment" and shown >= len(solutions):
        await state.update_data(index=int(data.get("index") or 0) + 1)
        await _send_current_problem(callback.message, state, session)


@router.callback_query(LearnCB.filter(F.action == "skip"), Learn.waiting_answer)
async def skip_problem(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    if data.get("stage") != "training":
        await callback.answer("Пропуск только в тренировке", show_alert=True)
        return
    problem_id = data.get("current_problem_id")
    if problem_id:
        await repos.add_attempt(
            session,
            user_id=callback.from_user.id,
            session_id=data["session_id"],
            problem_id=problem_id,
            submitted="[skip]",
            is_correct=False,
            used_help=False,
        )
    difficulty = int(data.get("current_difficulty") or 1)
    ok = await _send_training_problem(
        callback.message,
        state,
        session,
        difficulty=difficulty,
        user_id=callback.from_user.id,
        exclude_session_used=False,
    )
    if not ok:
        await callback.answer(
            "Других задач этого уровня сейчас нет. Реши эту или повысь уровень.",
            show_alert=True,
        )
        return
    await callback.answer("Следующее задание")


@router.callback_query(LearnCB.filter(F.action == "report"), Learn.waiting_answer)
async def report_problem(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    problem_id = data.get("current_problem_id")
    if not problem_id:
        await callback.answer("Нет текущего задания", show_alert=True)
        return
    await repos.flag_problem(session, int(problem_id))
    await callback.answer(
        "Спасибо. Задание отмечено, репетитор проверит условие и ответ.",
        show_alert=True,
    )


@router.message(
    Learn.waiting_answer,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_(NAV_BUTTONS),
)
async def handle_answer(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    problem_id = data.get("current_problem_id")
    if not problem_id:
        return
    problem = await repos.get_problem(session, problem_id)
    if problem is None:
        await message.answer("Задание потерялось, выбери тему заново.")
        return
    await delete_quietly(message.bot, message.chat.id, [message.message_id])
    ok = check_answer(problem.answer_type, problem.correct_answer, message.text or "")
    attempt_count = int(data.get("attempt_count") or 0) + 1
    used_help = bool(data.get("used_help"))
    await repos.add_attempt(
        session,
        user_id=message.from_user.id,
        session_id=data["session_id"],
        problem_id=problem.id,
        submitted=message.text,
        is_correct=ok,
        used_help=used_help,
    )
    await repos.touch_problem_stat(
        session, message.from_user.id, problem.id, solved=ok
    )
    stage = data.get("stage")
    if ok:
        if stage == "reinforcement":
            await apply_reinforcement_result(
                session, message.from_user.id, problem, True
            )
            await state.update_data(index=int(data.get("index") or 0) + 1)
            await _send_current_problem(message, state, session)
            return
        if stage == "assessment":
            await state.update_data(index=int(data.get("index") or 0) + 1)
            await _send_current_problem(message, state, session)
            return
        topic_id = data.get("topic_id")
        nxt = await _next_difficulty(session, topic_id, problem.difficulty)
        prev = await _prev_difficulty(session, topic_id, problem.difficulty)
        await state.update_data(
            can_level_up=nxt is not None, can_level_down=prev is not None
        )
        await _edit_problem(
            message,
            state,
            f"Верно.\n\nТренировка · {_difficulty_title(problem.difficulty)}",
            None,
        )
        sent = await message.answer(
            "Верно. Выбери, что дальше:",
            reply_markup=training_reply_keyboard(
                can_level_up=nxt is not None,
                can_level_down=prev is not None,
                admin=is_admin(message.from_user.id),
            ),
        )
        await nav.attach_ids(state, [sent.message_id])
        await nav.adopt_reply_kb(
            message.bot, message.chat.id, state, sent.message_id
        )
        return

    if stage == "reinforcement" and attempt_count >= WRONG_ATTEMPTS_BEFORE_HELP:
        await apply_reinforcement_result(session, message.from_user.id, problem, False)

    await state.update_data(attempt_count=attempt_count)
    data = await state.get_data()
    hints = await repos.list_hint_bodies(session, problem)
    solutions = await repos.list_solution_bodies(session, problem)
    sent = await message.bot.send_message(
        message.chat.id,
        "<i>Пока неверно. Попробуй ещё раз.</i>",
    )
    await track_ephemeral(state, sent.message_id, control=False)
    await _refresh_problem_keyboard(
        message,
        state,
        _problem_keyboard(
            data,
            hint_total=len(hints),
            solution_total=len(solutions),
            show_report=True,
        ),
    )
