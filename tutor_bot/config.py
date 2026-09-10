import os
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv()


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _admin_ids() -> frozenset[int]:
    raw = os.getenv("ADMIN_IDS", "")
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            ids.add(int(part))
    return frozenset(ids)


BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _int_env("DB_PORT", 3306)
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "tutor_bot")

ADMIN_IDS = _admin_ids()
TRIAL_DAYS = _int_env("TRIAL_DAYS", 3)
STARS_PRICE = _int_env("STARS_PRICE", 0)
REDIS_URL = os.getenv("REDIS_URL") or None
WRONG_ATTEMPTS_BEFORE_HELP = _int_env("WRONG_ATTEMPTS_BEFORE_HELP", 2)
POOL_SIZE = _int_env("DB_POOL_SIZE", 20)
POOL_MAX_OVERFLOW = _int_env("DB_POOL_MAX_OVERFLOW", 40)

DATABASE_URL = (
    f"mysql+asyncmy://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{quote_plus(DB_NAME)}?charset=utf8mb4"
)
