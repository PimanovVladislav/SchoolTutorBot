from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tutor_bot.db.models import Topic

BTN_CONTINUE = "Продолжить обучение"
BTN_TOPICS = "Выбрать тему"
BTN_PROGRESS = "Мой прогресс"
BTN_SUB = "Подписка"


class GradeCB(CallbackData, prefix="g"):
    grade: int


class TopicCB(CallbackData, prefix="t"):
    action: str
    topic_id: int


class LearnCB(CallbackData, prefix="l"):
    action: str


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CONTINUE)],
            [KeyboardButton(text=BTN_TOPICS), KeyboardButton(text=BTN_PROGRESS)],
            [KeyboardButton(text=BTN_SUB)],
        ],
        resize_keyboard=True,
    )


def grade_keyboard(grades: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for grade in grades:
        builder.button(text=f"{grade} класс", callback_data=GradeCB(grade=grade))
    builder.adjust(2)
    return builder.as_markup()


def topics_keyboard(topics: list[Topic]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for topic in topics:
        builder.button(
            text=f"{topic.grade} кл. · {topic.title}",
            callback_data=TopicCB(action="open", topic_id=topic.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def theory_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="К тренировке",
                    callback_data=LearnCB(action="training").pack(),
                )
            ]
        ]
    )


def after_training_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Начать проверочную",
                    callback_data=LearnCB(action="assessment").pack(),
                )
            ]
        ]
    )


def answer_keyboard(
    *,
    show_help: bool,
    can_skip: bool,
    show_hint: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    extras: list[InlineKeyboardButton] = []
    if show_hint:
        extras.append(
            InlineKeyboardButton(
                text="Подсказка", callback_data=LearnCB(action="hint").pack()
            )
        )
    if show_help:
        extras.append(
            InlineKeyboardButton(
                text="Помощь · разбор", callback_data=LearnCB(action="help").pack()
            )
        )
    if extras:
        rows.append(extras)
    if can_skip:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Пропустить", callback_data=LearnCB(action="skip").pack()
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subscription_keyboard(stars_price: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if stars_price > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"Оплатить {stars_price} ⭐ на 30 дней",
                    callback_data=LearnCB(action="pay").pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else InlineKeyboardMarkup(inline_keyboard=[])
