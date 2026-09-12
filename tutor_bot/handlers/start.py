from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.db import repos
from tutor_bot.db.models import Subject
from tutor_bot.handlers.common import ensure_user, greeting_name
from tutor_bot.keyboards import (
    GradeCB,
    SubjectCB,
    grade_keyboard,
    menu_for,
    subject_keyboard,
)
from tutor_bot.services.access import access_label, check_access
from tutor_bot.services import nav
from tutor_bot.states import Onboarding

router = Router()

INTRO = (
    "Я репетитор в Telegram: сначала теория по теме, потом проверочная с оценкой.\n\n"
    "«Продолжить обучение» — темы, которые ещё не сданы.\n"
    "«Мой прогресс» — успешно сданные темы и история оценок.\n"
    "«Настройки» — сменить класс или предмет."
)


@router.message(CommandStart())
async def cmd_start(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await nav.wipe_ui(message.bot, message.chat.id, state)
    await state.clear()
    user = await ensure_user(session, message.from_user)
    access = await check_access(session, user)
    name = greeting_name(user)
    if user.grade is None or user.track_id is None:
        await _ask_subject(
            message,
            state,
            session,
            prefix=f"Привет, {name}!\n\n{INTRO}\n\n",
        )
        return
    await message.answer(
        f"С возвращением, {name}!\n"
        f"Класс: {user.grade}. Доступ: {access_label(access)}.\n\n"
        f"{INTRO}",
        reply_markup=menu_for(user.id),
    )


async def _ask_subject(
    message: Message, state: FSMContext, session: AsyncSession, *, prefix: str = ""
) -> None:
    subjects = list(await repos.list_subjects(session))
    if not subjects:
        await message.answer("Программа ещё не загружена. Напиши репетитору.")
        return
    await state.set_state(Onboarding.subject)
    sent = await message.answer(
        prefix + "Выбери предмет:",
        reply_markup=subject_keyboard(subjects),
    )
    await nav.reset_stack(state, {"s": "subjects"})
    await nav.attach_ids(state, [sent.message_id])
    await nav.apply_reply_keyboard(message, menu_for(message.from_user.id))


@router.callback_query(SubjectCB.filter(), Onboarding.subject)
async def onboarding_subject(
    callback: CallbackQuery,
    callback_data: SubjectCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(subject_id=callback_data.subject_id)
    await state.set_state(Onboarding.grade)
    grades = await repos.list_grades(session)
    await nav.goto(state, {"s": "grades"})
    sent = await callback.message.answer(
        "Выбери класс. Прогресс по другим классам и предметам сохранится.",
        reply_markup=grade_keyboard(grades),
    )
    await nav.attach_ids(state, [sent.message_id])
    await callback.answer()


@router.callback_query(GradeCB.filter(), Onboarding.grade)
async def onboarding_grade(
    callback: CallbackQuery,
    callback_data: GradeCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await ensure_user(session, callback.from_user)
    data = await state.get_data()
    subject_id = data.get("subject_id")
    if subject_id:
        track = await repos.default_track_for_subject(session, int(subject_id))
    else:
        track = await repos.get_math_school_track(session)
    if track is None:
        await callback.answer("Программа ещё не загружена", show_alert=True)
        return
    await repos.set_user_grade_and_track(
        session, user.id, callback_data.grade, track.id
    )
    from_settings = bool(data.get("from_settings"))
    await nav.wipe_ui(callback.bot, callback.message.chat.id, state)
    await state.clear()
    subject = await session.get(Subject, track.subject_id)
    title = subject.title if subject else "предмет"
    text = (
        "Класс и предмет обновлены."
        if from_settings
        else f"Готово: {callback_data.grade} класс, {title}.\n"
        "Можно заниматься. Нажми «Продолжить обучение» или «Мой прогресс»."
    )
    await callback.message.answer(text, reply_markup=menu_for(user.id))
    await callback.answer()


@router.message(Command("class"))
async def cmd_class(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.update_data(from_settings=True)
    await _ask_subject(message, state, session)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Ок, текущее действие сброшено.",
        reply_markup=menu_for(message.from_user.id),
    )
