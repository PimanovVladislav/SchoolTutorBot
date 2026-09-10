from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext


async def track_theory(state: FSMContext, message_id: int) -> None:
    data = await state.get_data()
    ids = list(data.get("theory_message_ids") or [])
    if message_id not in ids:
        ids.append(message_id)
    await state.update_data(theory_message_ids=ids, theory_message_id=message_id)


async def track_ephemeral(state: FSMContext, message_id: int | None) -> None:
    if not message_id:
        return
    data = await state.get_data()
    ids = list(data.get("ephemeral_ids") or [])
    if message_id not in ids:
        ids.append(message_id)
    await state.update_data(ephemeral_ids=ids, current_problem_message_id=message_id)


async def wipe_ephemeral(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    ids = list(data.get("ephemeral_ids") or [])
    await delete_quietly(bot, chat_id, ids)
    await state.update_data(ephemeral_ids=[], current_problem_message_id=None)


async def wipe_lesson(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    ids = list(data.get("ephemeral_ids") or [])
    ids.extend(data.get("theory_message_ids") or [])
    theory_id = data.get("theory_message_id")
    if theory_id:
        ids.append(theory_id)
    await delete_quietly(bot, chat_id, ids)
    await state.update_data(
        ephemeral_ids=[],
        theory_message_ids=[],
        theory_message_id=None,
        current_problem_message_id=None,
    )


async def delete_quietly(bot: Bot, chat_id: int, ids: list[int]) -> None:
    unique = [item for item in dict.fromkeys(ids) if item]
    if not unique:
        return
    try:
        await bot.delete_messages(chat_id, unique)
        return
    except TelegramAPIError:
        pass
    for message_id in unique:
        try:
            await bot.delete_message(chat_id, message_id)
        except TelegramAPIError:
            pass
