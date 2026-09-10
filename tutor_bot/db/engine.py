from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tutor_bot.config import DATABASE_URL, POOL_MAX_OVERFLOW, POOL_SIZE

engine = create_async_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=POOL_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
)

session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
