import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

_USER_ERROR = "Не получилось обработать запрос. Нажми /start или попробуй ещё раз."


async def on_error(event: ErrorEvent) -> None:
    logger.exception("Update failed: %s", event.exception)
    update = event.update
    try:
        if update.callback_query:
            try:
                await update.callback_query.answer(
                    "Ошибка, попробуй ещё раз", show_alert=True
                )
            except TelegramBadRequest:
                pass
            if update.callback_query.message:
                await update.callback_query.message.answer(_USER_ERROR)
            return
        if update.message:
            await update.message.answer(_USER_ERROR)
    except TelegramBadRequest:
        logger.warning("Could not notify user about the error")
