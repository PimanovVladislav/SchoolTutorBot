from html import escape
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.config import ADMIN_IDS
from tutor_bot.db import repos
from tutor_bot.db.models import User
from tutor_bot.services.access import check_access


TELEGRAM_LIMIT = 3900


def split_html(text: str) -> list[str]:
    if len(text) <= TELEGRAM_LIMIT:
        return [text]
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= TELEGRAM_LIMIT:
            chunks.append(rest)
            break
        cut = rest.rfind("\n", 0, TELEGRAM_LIMIT)
        if cut < 200:
            cut = TELEGRAM_LIMIT
        chunks.append(rest[:cut])
        rest = rest[cut:].lstrip("\n")
    return chunks


def greeting_name(user: User) -> str:
    return escape(user.first_name or user.username or "ученик")


async def ensure_user(session: AsyncSession, tg_user) -> User:
    role = "admin" if tg_user.id in ADMIN_IDS else "student"
    return await repos.upsert_user(
        session,
        tg_user.id,
        tg_user.username,
        tg_user.first_name,
        tg_user.last_name,
        role=role,
    )


def access_denied_text() -> str:
    return (
        "Доступ к занятиям пока закрыт.\n\n"
        "Оплати месячную подписку в разделе «Подписка» или напиши репетитору — "
        "после оплаты доступ откроется."
    )


async def require_access(session: AsyncSession, user: User) -> Optional[str]:
    info = await check_access(session, user)
    if info.allowed:
        return None
    return access_denied_text()
