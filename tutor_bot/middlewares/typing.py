from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.chat_action import ChatActionSender


class TypingMiddleware(BaseMiddleware):
    """Пока хендлер работает, в чате висит «печатает…»."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        chat_id = _chat_id(event)
        if bot is None or chat_id is None:
            return await handler(event, data)
        async with ChatActionSender.typing(
            bot=bot, chat_id=chat_id, initial_sleep=0.25
        ):
            return await handler(event, data)


def _chat_id(event: TelegramObject) -> int | None:
    if isinstance(event, Message):
        return event.chat.id
    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        return event.message.chat.id
    return None
