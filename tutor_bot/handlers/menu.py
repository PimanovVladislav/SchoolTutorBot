from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.db import repos
from tutor_bot.handlers.common import ensure_user, require_access
from tutor_bot.keyboards import (
    BTN_CONTINUE,
    BTN_PROGRESS,
    BTN_SUB,
    BTN_TOPICS,
    grade_keyboard,
    main_menu,
    topics_keyboard,
)
from tutor_bot.services.scoring import MASTERY_LABELS
from tutor_bot.states import Onboarding

router = Router()


@router.message(F.text == BTN_CONTINUE)
@router.message(Command("learn"))
async def continue_learning(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    from tutor_bot.handlers.learn import start_topic

    user = await ensure_user(session, message.from_user)
    if user.grade is None or user.track_id is None:
        await state.set_state(Onboarding.grade)
        await message.answer(
            "Сначала выбери класс.", reply_markup=grade_keyboard([6, 7, 8, 9])
        )
        return
    denied = await require_access(session, user)
    if denied:
        await message.answer(denied, reply_markup=main_menu())
        return
    topic = await _continue_topic(session, user)
    if topic is None:
        await message.answer(
            "Для твоего класса пока нет тем. Напиши репетитору.",
            reply_markup=main_menu(),
        )
        return
    await start_topic(message, state, session, user, topic)


@router.message(F.text == BTN_TOPICS)
@router.message(Command("topics"))
async def list_topics(message: Message, session: AsyncSession) -> None:
    user = await ensure_user(session, message.from_user)
    denied = await require_access(session, user)
    if denied:
        await message.answer(denied, reply_markup=main_menu())
        return
    if user.grade is None or user.track_id is None:
        await message.answer("Сначала пройди /start и выбери класс.")
        return
    topics = await repos.list_topics_for_grade(session, user.track_id, user.grade)
    if not topics:
        await message.answer("Темы ещё не загружены.")
        return
    await message.answer("Выбери тему:", reply_markup=topics_keyboard(list(topics)))


@router.message(F.text == BTN_PROGRESS)
@router.message(Command("progress"))
async def show_progress(message: Message, session: AsyncSession) -> None:
    user = await ensure_user(session, message.from_user)
    if user.grade is None or user.track_id is None:
        await message.answer("Сначала выбери класс через /start.")
        return
    rows = await repos.list_progress_with_topics(
        session, user.id, user.track_id, user.grade
    )
    if not rows:
        await message.answer("Для твоего класса пока нет тем.")
        return
    lines = [f"<b>Прогресс · {user.grade} класс, математика</b>\n"]
    for topic, progress in rows:
        if progress is None:
            lines.append(f"• {topic.title} — ещё не начата")
            continue
        mastery = MASTERY_LABELS.get(progress.mastery, progress.mastery)
        score = (
            f", проверка {progress.assessment_score:.0f}%"
            if progress.assessment_score is not None
            else ""
        )
        reinf = ""
        if progress.reinforcement_total:
            reinf = (
                f", закрепление {progress.reinforcement_correct}/"
                f"{progress.reinforcement_total}"
            )
        lines.append(f"• {topic.title} — {mastery}{score}{reinf}")
    await message.answer("\n".join(lines), reply_markup=main_menu())


@router.message(F.text == BTN_SUB)
@router.message(Command("subscribe"))
async def show_subscription(message: Message, session: AsyncSession) -> None:
    from tutor_bot.handlers.subscription import send_subscription_card

    user = await ensure_user(session, message.from_user)
    await send_subscription_card(message, session, user)


async def _continue_topic(session: AsyncSession, user):
    if user.current_topic_id:
        current = await repos.get_topic(session, user.current_topic_id)
        if current is not None:
            progress = await repos.get_or_create_progress(
                session, user.id, current.id
            )
            if progress.assessment_score is None:
                return current
    rows = await repos.list_progress_with_topics(
        session, user.id, user.track_id, user.grade
    )
    for topic, progress in rows:
        if progress is None or progress.assessment_score is None:
            return topic
    return rows[-1][0] if rows else None
