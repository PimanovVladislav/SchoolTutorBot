from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.db import repos
from tutor_bot.handlers.common import ensure_user, greeting_name
from tutor_bot.keyboards import GradeCB, grade_keyboard, main_menu
from tutor_bot.services.access import access_label, check_access
from tutor_bot.states import Onboarding

router = Router()

INTRO = (
    "Я репетитор по школьной математике в Telegram.\n\n"
    "Как устроены занятия:\n"
    "1) Разбор темы — коротко и по делу.\n"
    "2) Тренировка — можно ошибаться и смотреть разбор.\n"
    "3) Проверочная — из неё складывается оценка по теме.\n"
    "4) Закрепление — старые задачи всплывают в новых темах.\n\n"
    "На каждую тему копится оценка и уровень понимания."
)


@router.message(CommandStart())
async def cmd_start(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.clear()
    user = await ensure_user(session, message.from_user)
    access = await check_access(session, user)
    name = greeting_name(user)
    if user.grade is None:
        await state.set_state(Onboarding.grade)
        await message.answer(
            f"Привет, {name}!\n\n{INTRO}\n\nВыбери класс, чтобы подобрать программу:",
            reply_markup=grade_keyboard([6, 7, 8, 9]),
        )
        return
    await message.answer(
        f"С возвращением, {name}!\n"
        f"Класс: {user.grade}. Доступ: {access_label(access)}.\n\n"
        f"{INTRO}",
        reply_markup=main_menu(),
    )


@router.callback_query(GradeCB.filter(), Onboarding.grade)
async def onboarding_grade(
    callback: CallbackQuery,
    callback_data: GradeCB,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await ensure_user(session, callback.from_user)
    track = await repos.get_math_school_track(session)
    if track is None:
        await callback.answer("Программа ещё не загружена", show_alert=True)
        return
    await repos.set_user_grade_and_track(session, user.id, callback_data.grade, track.id)
    await state.clear()
    await callback.message.edit_text(
        f"Отлично, {callback_data.grade} класс, математика.\n"
        "Когда появятся физика, ОГЭ/ЕГЭ и другие треки — они будут в этом же меню."
    )
    await callback.message.answer(
        "Можно начинать. Нажми «Продолжить обучение» или выбери тему.",
        reply_markup=main_menu(),
    )
    await callback.answer()


@router.message(Command("class"))
async def cmd_class(message: Message, state: FSMContext) -> None:
    await state.set_state(Onboarding.grade)
    await message.answer(
        "Выбери класс — программа подстроится:",
        reply_markup=grade_keyboard([6, 7, 8, 9]),
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "Ок, задание сброшено. Можно выбрать тему заново.",
        reply_markup=main_menu(),
    )
