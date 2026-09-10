import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from tutor_bot.config import BOT_TOKEN, REDIS_URL
from tutor_bot.content import seed_curriculum
from tutor_bot.db.engine import engine, session_factory
from tutor_bot.db.migrate import apply_schema
from tutor_bot.handlers.errors import on_error
from tutor_bot.handlers import setup_routers
from tutor_bot.middlewares import DbSessionMiddleware, TypingMiddleware
from tutor_bot.services.status import notify_admins

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _storage():
    if REDIS_URL:
        from aiogram.fsm.storage.redis import RedisStorage

        logger.info("FSM storage: Redis")
        return RedisStorage.from_url(REDIS_URL)
    logger.info("FSM storage: memory (для нескольких процессов укажи REDIS_URL)")
    return MemoryStorage()


async def _init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(apply_schema)
    async with session_factory() as session:
        await seed_curriculum(session)
        await session.commit()
    logger.info("Database ready, curriculum seeded")


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начало и выбор класса"),
            BotCommand(command="learn", description="Продолжить обучение"),
            BotCommand(command="topics", description="Выбрать тему"),
            BotCommand(command="progress", description="Мой прогресс"),
            BotCommand(command="subscribe", description="Подписка"),
            BotCommand(command="cancel", description="Сбросить текущее задание"),
        ]
    )


async def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Скопируй .env.example в .env")

    await _init_db()
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=_storage())
    dp.error.register(on_error)
    dp.update.middleware(DbSessionMiddleware(session_factory))
    dp.message.middleware(TypingMiddleware())
    dp.callback_query.middleware(TypingMiddleware())
    dp.include_router(setup_routers())

    await _set_commands(bot)
    logger.info("Bot polling started")
    try:
        await notify_admins(bot, "Бот запущен")
        await dp.start_polling(bot)
    finally:
        try:
            await notify_admins(bot, "Бот выключен")
        except Exception:
            logger.exception("Failed to notify admins about shutdown")
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBye!")
