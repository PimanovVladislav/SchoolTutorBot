import asyncio
import logging

from aiogram import Bot

from tutor_bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, text: str) -> None:
    for user_id in ADMIN_IDS:
        try:
            await bot.send_message(user_id, text)
        except Exception:
            logger.debug("Could not notify admin %s", user_id)
        await asyncio.sleep(0.04)
