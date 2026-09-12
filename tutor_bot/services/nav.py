from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from tutor_bot.services.chat import delete_quietly

HOME_TEXT = "Главное меню. Выберите действие:"


def screen_key(screen: dict) -> dict:
    return {key: value for key, value in screen.items() if key != "ids"}


async def get_stack(state: FSMContext) -> list[dict]:
    return list((await state.get_data()).get("nav") or [])


async def set_stack(state: FSMContext, screens: list[dict]) -> None:
    await state.update_data(nav=screens)


async def reset_stack(state: FSMContext, screen: dict) -> None:
    await set_stack(state, [{**screen_key(screen), "ids": []}])


async def goto(state: FSMContext, screen: dict) -> None:
    stack = await get_stack(state)
    key = screen_key(screen)
    if stack and screen_key(stack[-1]) == key:
        return
    stack.append({**key, "ids": []})
    await set_stack(state, stack)


async def replace_top(state: FSMContext, screen: dict) -> dict | None:
    stack = await get_stack(state)
    previous = stack.pop() if stack else None
    stack.append({**screen_key(screen), "ids": []})
    await set_stack(state, stack)
    return previous


async def pop_screen(state: FSMContext) -> dict | None:
    stack = await get_stack(state)
    if not stack:
        return None
    current = stack.pop()
    await set_stack(state, stack)
    return current


async def track_ui(state: FSMContext, ids: list[int]) -> None:
    data = await state.get_data()
    stored = list(data.get("ui_ids") or [])
    for item in ids:
        if item and item not in stored:
            stored.append(item)
    await state.update_data(ui_ids=stored)


async def attach_ids(state: FSMContext, ids: list[int]) -> None:
    clean = [item for item in ids if item]
    if not clean:
        return
    stack = await get_stack(state)
    if stack:
        existing = list(stack[-1].get("ids") or [])
        for item in clean:
            if item not in existing:
                existing.append(item)
        stack[-1]["ids"] = existing
        await set_stack(state, stack)
    await track_ui(state, clean)


async def collect_ui_ids(state: FSMContext) -> list[int]:
    data = await state.get_data()
    ids: list[int] = []
    for key in (
        "ui_ids",
        "theory_message_ids",
        "ephemeral_ids",
        "exam_question_ids",
        "exam_panel_ids",
    ):
        ids.extend(data.get(key) or [])
    for extra in (
        data.get("theory_message_id"),
        data.get("current_problem_message_id"),
    ):
        if extra:
            ids.append(int(extra))
    for screen in data.get("nav") or []:
        ids.extend(screen.get("ids") or [])
    unique: list[int] = []
    seen: set[int] = set()
    for item in ids:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


async def wipe_ui(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    extra: list[int] | None = None,
) -> None:
    ids = await collect_ui_ids(state)
    if extra:
        ids.extend(extra)
    await delete_quietly(bot, chat_id, ids)
    await state.update_data(
        ui_ids=[],
        nav=[],
        ephemeral_ids=[],
        theory_message_ids=[],
        theory_message_id=None,
        current_problem_message_id=None,
        exam_question_ids=[],
        exam_panel_ids=[],
        exam_attempt_id=None,
        exam_problem_id=None,
        result_expanded=0,
    )


async def apply_reply_keyboard(target: Message, markup) -> None:
    try:
        stub = await target.answer("\u2063", reply_markup=markup)
        await stub.delete()
    except TelegramBadRequest:
        await target.answer("Меню обновлено.", reply_markup=markup)
