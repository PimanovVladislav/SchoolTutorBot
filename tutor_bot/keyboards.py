from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tutor_bot.db.models import Topic, TopicProgress

BTN_CONTINUE = "Продолжить обучение"
BTN_TOPICS = "Выбрать тему"
BTN_PROGRESS = "Мой прогресс"
BTN_SUB = "Подписка"
BTN_ADMIN = "Админка"
BTN_ADMIN_CONTENT = "Контент"
BTN_ADMIN_STUDENTS = "Ученики"
BTN_ADMIN_FLAGS = "Жалобы на задания"
BTN_ADMIN_GRANT = "Выдать доступ"
BTN_ADMIN_BACK = "В меню ученика"
BTN_ADMIN_SUBJECT = "Добавить предмет"
BTN_ADMIN_GRADE = "Добавить класс"
BTN_ADMIN_TOPIC = "Добавить тему"
BTN_ADMIN_PROBLEM = "Добавить задание"
BTN_ADMIN_THEORY_MORE = "Ещё редакция теории"
BTN_ADMIN_HINT_MORE = "Ещё подсказка"
BTN_ADMIN_SOLUTION_MORE = "Ещё разбор"
BTN_CANCEL = "Отмена"

DIFFICULTY_LABELS = {
    1: "лёгкий",
    2: "средний",
    3: "сложный",
}


class GradeCB(CallbackData, prefix="g"):
    grade: int


class TopicCB(CallbackData, prefix="t"):
    action: str
    topic_id: int


class LearnCB(CallbackData, prefix="l"):
    action: str


class AdminCB(CallbackData, prefix="ad"):
    a: str
    i: int = 0


NAV_BUTTONS = {
    BTN_CONTINUE,
    BTN_PROGRESS,
    BTN_SUB,
    BTN_TOPICS,
    BTN_ADMIN,
    BTN_ADMIN_CONTENT,
    BTN_ADMIN_STUDENTS,
    BTN_ADMIN_FLAGS,
    BTN_ADMIN_GRANT,
    BTN_ADMIN_BACK,
    BTN_ADMIN_SUBJECT,
    BTN_ADMIN_GRADE,
    BTN_ADMIN_TOPIC,
    BTN_ADMIN_PROBLEM,
    BTN_ADMIN_THEORY_MORE,
    BTN_ADMIN_HINT_MORE,
    BTN_ADMIN_SOLUTION_MORE,
    BTN_CANCEL,
}


def main_menu(*, admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=BTN_CONTINUE)],
        [KeyboardButton(text=BTN_TOPICS), KeyboardButton(text=BTN_PROGRESS)],
        [KeyboardButton(text=BTN_SUB)],
    ]
    if admin:
        keyboard.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def menu_for(user_id: int) -> ReplyKeyboardMarkup:
    from tutor_bot.config import ADMIN_IDS

    return main_menu(admin=user_id in ADMIN_IDS)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_ADMIN_CONTENT),
                KeyboardButton(text=BTN_ADMIN_STUDENTS),
            ],
            [
                KeyboardButton(text=BTN_ADMIN_FLAGS),
                KeyboardButton(text=BTN_ADMIN_GRANT),
            ],
            [KeyboardButton(text=BTN_ADMIN_BACK)],
        ],
        resize_keyboard=True,
    )


def admin_content_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BTN_ADMIN_SUBJECT),
                KeyboardButton(text=BTN_ADMIN_GRADE),
            ],
            [
                KeyboardButton(text=BTN_ADMIN_TOPIC),
                KeyboardButton(text=BTN_ADMIN_PROBLEM),
            ],
            [KeyboardButton(text=BTN_ADMIN_THEORY_MORE)],
            [
                KeyboardButton(text=BTN_ADMIN_HINT_MORE),
                KeyboardButton(text=BTN_ADMIN_SOLUTION_MORE),
            ],
            [KeyboardButton(text=BTN_ADMIN_BACK)],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def grade_keyboard(grades: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for grade in grades:
        builder.button(text=f"{grade} класс", callback_data=GradeCB(grade=grade))
    builder.adjust(2)
    return builder.as_markup()


def progress_label(progress: TopicProgress | None) -> str:
    if progress is None or progress.mastery == "not_started":
        return "—"
    if progress.assessment_score is None:
        return "…"
    score = int(round(progress.assessment_score))
    if score >= 70:
        return f"✓ {score}%"
    return f"{score}%"


def topics_keyboard(
    rows: list[tuple[Topic, TopicProgress | None]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for topic, progress in rows:
        title = topic.title if len(topic.title) <= 48 else topic.title[:45] + "…"
        builder.button(
            text=title,
            callback_data=TopicCB(action="open", topic_id=topic.id),
        )
        builder.button(
            text=progress_label(progress),
            callback_data=TopicCB(action="open", topic_id=topic.id),
        )
    builder.adjust(2)
    return builder.as_markup()


def theory_keyboard(*, has_more: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="К тренировке",
                callback_data=LearnCB(action="training").pack(),
            )
        ]
    ]
    if has_more:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Всё ещё непонятно",
                    callback_data=LearnCB(action="theory_more").pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def after_correct_training_keyboard(*, can_level_up: bool) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(
            text="Решить ещё", callback_data=LearnCB(action="more").pack()
        )
    ]
    if can_level_up:
        row.append(
            InlineKeyboardButton(
                text="Повысить уровень",
                callback_data=LearnCB(action="level_up").pack(),
            )
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [
                InlineKeyboardButton(
                    text="К проверочной",
                    callback_data=LearnCB(action="assessment").pack(),
                )
            ],
        ]
    )


def answer_keyboard(
    *,
    show_help: bool,
    can_skip: bool,
    show_hint: bool,
    show_report: bool = False,
    show_hint_more: bool = False,
    show_help_more: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    extras: list[InlineKeyboardButton] = []
    if show_hint:
        extras.append(
            InlineKeyboardButton(
                text="Подсказка", callback_data=LearnCB(action="hint").pack()
            )
        )
    elif show_hint_more:
        extras.append(
            InlineKeyboardButton(
                text="Всё ещё непонятно",
                callback_data=LearnCB(action="hint").pack(),
            )
        )
    if show_help:
        extras.append(
            InlineKeyboardButton(
                text="Помощь · разбор", callback_data=LearnCB(action="help").pack()
            )
        )
    elif show_help_more:
        extras.append(
            InlineKeyboardButton(
                text="Всё ещё не понял",
                callback_data=LearnCB(action="help").pack(),
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
    if show_report:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Сообщить об ошибке задания/ответа",
                    callback_data=LearnCB(action="report").pack(),
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
    return (
        InlineKeyboardMarkup(inline_keyboard=rows)
        if rows
        else InlineKeyboardMarkup(inline_keyboard=[])
    )


def admin_pick_keyboard(action: str, items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item_id, title in items:
        label = title if len(title) <= 48 else title[:45] + "…"
        builder.button(text=label, callback_data=AdminCB(a=action, i=item_id))
    builder.adjust(1)
    return builder.as_markup()


def admin_users_keyboard(offset: int, has_next: bool) -> InlineKeyboardMarkup:
    row: list[InlineKeyboardButton] = []
    if offset > 0:
        row.append(
            InlineKeyboardButton(
                text="Назад",
                callback_data=AdminCB(a="users", i=max(0, offset - 6)).pack(),
            )
        )
    if has_next:
        row.append(
            InlineKeyboardButton(
                text="Дальше",
                callback_data=AdminCB(a="users", i=offset + 6).pack(),
            )
        )
    return InlineKeyboardMarkup(inline_keyboard=[row] if row else [])


def admin_user_actions(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Выдать 30 дней",
                    callback_data=AdminCB(a="grant30", i=user_id).pack(),
                ),
                InlineKeyboardButton(
                    text="Забрать доступ",
                    callback_data=AdminCB(a="revoke", i=user_id).pack(),
                ),
            ]
        ]
    )

