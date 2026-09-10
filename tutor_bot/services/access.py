from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.config import ADMIN_IDS, TRIAL_DAYS
from tutor_bot.db import repos
from tutor_bot.db.models import User


@dataclass(frozen=True)
class AccessInfo:
    allowed: bool
    reason: str
    ends_at: Optional[datetime] = None


def is_admin(user_id: int, user: Optional[User] = None) -> bool:
    if user_id in ADMIN_IDS:
        return True
    return bool(user and user.role == "admin")


async def check_access(session: AsyncSession, user: User) -> AccessInfo:
    now = datetime.utcnow()
    if is_admin(user.id, user):
        return AccessInfo(True, "admin")

    sub = await repos.get_active_subscription(session, user.id, now)
    if sub:
        return AccessInfo(True, "subscription", sub.ends_at)

    if TRIAL_DAYS > 0 and user.created_at:
        trial_end = user.created_at + timedelta(days=TRIAL_DAYS)
        if now < trial_end:
            return AccessInfo(True, "trial", trial_end)

    return AccessInfo(False, "none")


def access_label(info: AccessInfo) -> str:
    if not info.allowed:
        return "нет активного доступа"
    if info.reason == "admin":
        return "администратор"
    if info.reason == "trial":
        until = info.ends_at.strftime("%d.%m.%Y") if info.ends_at else "—"
        return f"пробный период до {until}"
    until = info.ends_at.strftime("%d.%m.%Y") if info.ends_at else "—"
    return f"подписка до {until}"
