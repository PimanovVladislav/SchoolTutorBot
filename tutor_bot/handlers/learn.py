from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.config import WRONG_ATTEMPTS_BEFORE_HELP
from tutor_bot.db import repos
from tutor_bot.db.models import Topic, User
from tutor_bot.handlers.common import split_html
from tutor_bot.keyboards import (
    BTN_CONTINUE,
    BTN_PROGRESS,
    BTN_SUB,
    BTN_TOPICS,
    LearnCB,
    TopicCB,
    after_training_keyboard,
    answer_keyboard,
    main_menu,
    theory_keyboard,
)
from tutor_bot.services.answers import check_answer
from tutor_bot.services.learning import (
    apply_assessment_score,
    apply_reinforcement_result,
    build_start_queue,
    load_kind_queue,
)
from tutor_bot.services.scoring import MASTERY_LABELS
from tutor_bot.states import Learn

router = Router()

KIND_TITLES = {
    "reinforcement": "Закрепление",
    "training": "Тренировка",
    "assessment": "Проверочная",
}


async def start_topic(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    topic: Topic,
) -> None:
    await repos.set_current_topic(session, user.id, topic.id)
    learning = await repos.create_session(session, user.id, topic.id, stage="theory")
    progress = await repos.get_or_create_progress(session, user.id, topic.id)
    if progress.mastery == "not_started":
        progress.mastery = "learning"
    reinforcement_ids = await build_start_queue(
        session, user.id, topic, include_reinforcement=True
    )
    await state.set_state(Learn.waiting_answer)
    await state.update_data(
        session_id=learning.id,
        topic_id=topic.id,
        queue=[],
        index=0,
        attempt_count=0,
        used_help=False,
        hint_used=False,
        current_problem_id=None,
        stage="theory",
    )
    header = (
        f"<b>{topic.title}</b>\n"
        f"{topic.grade} класс · математика\n\n"
        f"{topic.summary}"
    )
    await message.answer(header, reply_markup=main_menu())
    if reinforcement_ids:
        await repos.set_session_stage(session, learning.id, "reinforcement")
        await state.update_data(stage="reinforcement", queue=reinforcement_ids, index=0)
        await message.answer(
            "Сначала короткое закрепление прошлых тем — затем новый материал."
        )
        await _send_current_problem(message, state, session)
        return
    await _send_theory(message, session, topic)


async def _send_theory(message: Message, session: AsyncSession, topic: Topic) -> None:
    progress = await repos.get_or_create_progress(session, message.chat.id, topic.id)
    progress.theory_done = True
    for chunk in split_html(topic.theory):
        await message.answer(chunk)
    await message.answer(
        "Когда разбор понятен — переходи к тренировке.",
        reply_markup=theory_keyboard(),
    )


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
    await state.update_data(
        current_problem_id=problem.id,
        attempt_count=0,
        used_help=False,
        hint_used=False,
    )
    title = KIND_TITLES.get(stage, "Задание")
    text = f"<b>{title}</b> · {index + 1}/{len(queue)}\n\n{problem.prompt}"
    await target.answer(
        text,
        reply_markup=answer_keyboard(
            show_help=False,
            can_skip=stage == "training",
            show_hint=bool(problem.hint),
        ),
    )


async def _finish_stage(
    target: Message, state: FSMContext, session: AsyncSession, stage: str
) -> None:
    data = await state.get_data()
    topic = await repos.get_topic(session, data["topic_id"])
    session_id = data["session_id"]
    if topic is None:
        await state.clear()
        await target.answer("Тема не найдена.", reply_markup=main_menu())
        return
    if stage == "reinforcement":
        await repos.set_session_stage(session, session_id, "theory")
        await state.update_data(stage="theory", queue=[], index=0)
        await _send_theory(target, session, topic)
        return
    if stage == "training":
        progress = await repos.get_or_create_progress(session, target.chat.id, topic.id)
        progress.training_done = True
        await repos.set_session_stage(session, session_id, "assessment")
        await state.update_data(stage="assessment_ready", queue=[], index=0)
        await state.set_state(Learn.waiting_answer)
        await target.answer(
            "Тренировка закончена. Дальше проверочная: оценка по теме "
            "считается по ней. Разбор после нескольких ошибок тоже доступен, "
            "но сильно снижает балл.",
            reply_markup=after_training_keyboard(),
        )
        return
    if stage == "assessment":
        problems = list(await repos.list_problems(session, topic.id, "assessment"))
        attempts = await repos.list_session_attempts(session, session_id)
        score = await apply_assessment_score(
            session, target.chat.id, topic.id, problems, attempts
        )
        await repos.finish_session(session, session_id)
        await state.clear()
        mastery = MASTERY_LABELS[repos_mastery(score)]
        await target.answer(
            f"<b>Проверочная закрыта</b>\n"
            f"Тема: {topic.title}\n"
            f"Оценка: {score:.0f}%\n"
            f"Уровень: {mastery}\n\n"
            "Посмотреть все темы — «Мой прогресс». "
            "Следующая тема — «Продолжить обучение».",
            reply_markup=main_menu(),
        )
        return
    await target.answer("Этап завершён.", reply_markup=main_menu())


def repos_mastery(score: float) -> str:
    from tutor_bot.services.scoring import mastery_from_score

    return mastery_from_score(score)


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
        await callback.message.answer(denied, reply_markup=main_menu())
        return
    topic = await repos.get_topic(session, callback_data.topic_id)
    if topic is None:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    await callback.answer()
    await start_topic(callback.message, state, session, user, topic)


@router.callback_query(LearnCB.filter(F.action == "training"), Learn.waiting_answer)
async def start_training(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if not topic_id:
        await callback.answer("Сначала выбери тему", show_alert=True)
        return
    queue = await load_kind_queue(session, topic_id, "training")
    if not queue:
        await callback.answer("В теме нет тренировочных задач", show_alert=True)
        return
    await repos.set_session_stage(session, data["session_id"], "training")
    await state.update_data(stage="training", queue=queue, index=0)
    await callback.answer()
    await _send_current_problem(callback.message, state, session)


@router.callback_query(LearnCB.filter(F.action == "assessment"), Learn.waiting_answer)
async def start_assessment(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    topic_id = data.get("topic_id")
    if not topic_id:
        await callback.answer("Сначала выбери тему", show_alert=True)
        return
    queue = await load_kind_queue(session, topic_id, "assessment")
    if not queue:
        await callback.answer("В теме нет проверочных задач", show_alert=True)
        return
    await repos.set_session_stage(session, data["session_id"], "assessment")
    await state.update_data(stage="assessment", queue=queue, index=0)
    await callback.answer()
    await callback.message.answer("Проверочная. Пиши ответ сообщением.")
    await _send_current_problem(callback.message, state, session)


@router.callback_query(LearnCB.filter(F.action == "hint"), Learn.waiting_answer)
async def show_hint(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    problem = await repos.get_problem(session, data.get("current_problem_id") or 0)
    if not problem or not problem.hint:
        await callback.answer("Подсказки нет", show_alert=True)
        return
    await state.update_data(hint_used=True)
    await callback.answer()
    await callback.message.answer(f"<b>Подсказка</b>\n{problem.hint}")


@router.callback_query(LearnCB.filter(F.action == "help"), Learn.waiting_answer)
async def show_help(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    data = await state.get_data()
    problem = await repos.get_problem(session, data.get("current_problem_id") or 0)
    if not problem:
        await callback.answer("Задание не найдено", show_alert=True)
        return
    await state.update_data(used_help=True)
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
        await apply_reinforcement_result(session, callback.from_user.id, problem, False)
    await callback.answer()
    await callback.message.answer(f"<b>Разбор</b>\n{problem.solution}")
    if data.get("stage") == "assessment":
        await state.update_data(index=int(data.get("index") or 0) + 1)
        await _send_current_problem(callback.message, state, session)
        return
    await callback.message.answer(
        "Можно ввести ответ ещё раз — для тренировки это полезно, "
        "но задание уже помечено как разобранное с помощью."
    )


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
    await state.update_data(index=int(data.get("index") or 0) + 1)
    await callback.answer("Пропущено")
    await _send_current_problem(callback.message, state, session)


@router.message(
    Learn.waiting_answer,
    F.text,
    ~F.text.startswith("/"),
    ~F.text.in_({BTN_CONTINUE, BTN_PROGRESS, BTN_SUB, BTN_TOPICS}),
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
    ok = check_answer(problem.answer_type, problem.correct_answer, message.text)
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
    stage = data.get("stage")
    if ok:
        if stage == "reinforcement":
            await apply_reinforcement_result(
                session, message.from_user.id, problem, True
            )
        await message.answer("Верно.")
        await state.update_data(index=int(data.get("index") or 0) + 1)
        await _send_current_problem(message, state, session)
        return

    if stage == "reinforcement" and attempt_count >= WRONG_ATTEMPTS_BEFORE_HELP:
        await apply_reinforcement_result(session, message.from_user.id, problem, False)

    await state.update_data(attempt_count=attempt_count)
    show_help = attempt_count >= WRONG_ATTEMPTS_BEFORE_HELP
    await message.answer(
        "Пока неверно. Проверь вычисления и попробуй ещё раз.",
        reply_markup=answer_keyboard(
            show_help=show_help,
            can_skip=stage == "training",
            show_hint=bool(problem.hint),
        ),
    )
