from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.config import ADMIN_IDS, STARS_PRICE
from tutor_bot.db import repos
from tutor_bot.handlers.common import ensure_user
from tutor_bot.keyboards import LearnCB, menu_for, subscription_keyboard
from tutor_bot.services.access import access_label, check_access, is_admin

router = Router()


async def send_subscription_card(
    message: Message, session: AsyncSession, user
) -> None:
    info = await check_access(session, user)
    text = (
        f"<b>Доступ</b>\n{access_label(info)}\n\n"
        "Месячный доступ открывает все темы твоего класса: разборы, "
        "тренировки, проверочные и закрепление."
    )
    if STARS_PRICE > 0:
        text += f"\n\nОплата в Telegram Stars: {STARS_PRICE} ⭐ за 30 дней."
    else:
        text += (
            "\n\nОплата пока вручную: напиши репетитору, после оплаты "
            "доступ включат командой."
        )
        if is_admin(user.id, user):
            text += (
                "\n\nАдмин: <code>/grant telegram_id_или_@username 30</code> — выдать 30 дней."
            )
    markup = subscription_keyboard(STARS_PRICE)
    await message.answer(
        text, reply_markup=markup if STARS_PRICE > 0 else menu_for(user.id)
    )


@router.message(Command("grant"))
async def cmd_grant(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = (message.text or "").split()
    if len(parts) < 3:
        await message.answer("Формат: /grant telegram_id_или_@username дни")
        return
    try:
        days = int(parts[2])
    except ValueError:
        await message.answer("Число дней должно быть числом.")
        return
    target = await repos.find_user(session, parts[1])
    if target is None and parts[1].lstrip("-").isdigit():
        target = await repos.upsert_user(session, int(parts[1]), None, None, None)
    if target is None:
        await message.answer("Пользователь ещё не писал боту. Пусть нажмёт /start.")
        return
    sub = await repos.grant_subscription(
        session, target.id, days, source="admin", now=datetime.utcnow()
    )
    await message.answer(
        f"Доступ пользователю {target.id} до {sub.ends_at.strftime('%d.%m.%Y %H:%M')} UTC."
    )
    try:
        await message.bot.send_message(
            target.id,
            f"Доступ открыт до {sub.ends_at.strftime('%d.%m.%Y')}. Можно заниматься.",
            reply_markup=menu_for(target.id),
        )
    except Exception:
        pass


@router.message(Command("revoke"))
async def cmd_revoke(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Формат: /revoke telegram_id")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return
    await repos.revoke_subscriptions(session, target_id)
    await message.answer(f"Доступ пользователя {target_id} отозван.")


@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    if message.from_user.id not in ADMIN_IDS:
        return
    total = await repos.count_users(session)
    await message.answer(f"Пользователей в базе: {total}")


@router.callback_query(LearnCB.filter(F.action == "pay"))
async def pay_stars(callback, session: AsyncSession) -> None:
    if STARS_PRICE <= 0:
        await callback.answer("Оплата через Stars не настроена", show_alert=True)
        return
    await callback.message.answer_invoice(
        title="Месяц занятий",
        description="Доступ к разборам, тренировкам и проверочным на 30 дней.",
        payload="sub_30",
        currency="XTR",
        prices=[LabeledPrice(label="30 дней", amount=STARS_PRICE)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery) -> None:
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: Message, session: AsyncSession) -> None:
    user = await ensure_user(session, message.from_user)
    payment = message.successful_payment
    await repos.grant_subscription(
        session,
        user.id,
        days=30,
        source="stars",
        now=datetime.utcnow(),
        payment_id=payment.telegram_payment_charge_id,
    )
    await message.answer(
        "Оплата прошла, доступ на 30 дней открыт. Можно заниматься.",
        reply_markup=menu_for(user.id),
    )
