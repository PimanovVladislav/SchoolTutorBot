from html import escape
import re

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tutor_bot.db.models import Topic, TopicProgress

# Telegram API: текст inline-кнопки не длиннее 64 символов.
# Если кнопок несколько в ряду, клиент ещё сильнее обрезает подпись и хинт.
BUTTON_TEXT_LIMIT = 64

BTN_CONTINUE = "Продолжить обучение"
BTN_PROGRESS = "Мой прогресс"
BTN_SETTINGS = "Настройки"
BTN_BACK = "Назад"
BTN_HOME = "На главную"
BTN_EXAM_FINISH = "Завершить работу"
BTN_TOPICS = "Выбрать тему"
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


class SubjectCB(CallbackData, prefix="sj"):
    subject_id: int


class GradeCB(CallbackData, prefix="g"):
    grade: int


class TopicCB(CallbackData, prefix="t"):
    action: str
    topic_id: int


class LearnCB(CallbackData, prefix="l"):
    action: str


class MenuCB(CallbackData, prefix="m"):
    a: str
    t: int = 0
    i: int = 0


class AdminCB(CallbackData, prefix="ad"):
    a: str
    i: int = 0


NAV_BUTTONS = {
    BTN_CONTINUE,
    BTN_PROGRESS,
    BTN_SETTINGS,
    BTN_BACK,
    BTN_HOME,
    BTN_EXAM_FINISH,
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
        [KeyboardButton(text=BTN_PROGRESS)],
        [KeyboardButton(text=BTN_SETTINGS)],
    ]
    if admin:
        keyboard.append([KeyboardButton(text=BTN_ADMIN)])
    keyboard.append([KeyboardButton(text=BTN_BACK), KeyboardButton(text=BTN_HOME)])
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


def nav_keyboard(*, back: bool = True) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=nav_rows(back=back))


def nav_rows(*, back: bool = True) -> list[list[InlineKeyboardButton]]:
    row: list[InlineKeyboardButton] = []
    if back:
        row.append(
            InlineKeyboardButton(text=BTN_BACK, callback_data=MenuCB(a="bk").pack())
        )
    row.append(
        InlineKeyboardButton(text=BTN_HOME, callback_data=MenuCB(a="hm").pack())
    )
    return [row]


def subject_keyboard(subjects: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subject in subjects:
        builder.button(
            text=fit_button_text(subject.title),
            callback_data=SubjectCB(subject_id=subject.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def grade_keyboard(grades: list[int]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for grade in grades:
        builder.button(text=f"{grade} класс", callback_data=GradeCB(grade=grade))
    builder.adjust(2)
    return builder.as_markup()


def fit_button_text(text: str, limit: int = BUTTON_TEXT_LIMIT) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def topics_catalog_html(items: list[tuple[int, str, str | None]]) -> str:
    """Полные названия в тексте: номер берётся из БД (порядок в классе)."""
    lines: list[str] = []
    for number, title, note in items:
        lines.append(f"<b>{number}.</b> {escape(title)}")
        if note:
            lines.append(f"<i>{escape(note)}</i>")
    return "\n".join(lines)


def learn_status_note(progress_text: str | None) -> str:
    if not progress_text:
        return "ещё не начата"
    if progress_text == "идёт":
        return "идёт проверочная"
    if progress_text == "…":
        return "начата"
    return f"последняя оценка: {progress_text}"


def passed_status_note(grade: str) -> str:
    return f"лучшая оценка: {grade}"


def learn_start_keyboard(start_number: int, topic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=fit_button_text(f"Начать с {start_number}"),
                    callback_data=MenuCB(a="st", t=topic_id).pack(),
                )
            ],
        ]
    )


def exam_start_keyboard(topic_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Приступить",
                    callback_data=MenuCB(a="go", t=topic_id).pack(),
                )
            ],
        ]
    )


def exam_task_button_text(sort_order: int, submitted: str | None) -> str:
    status = "ответ отправлен" if (submitted or "").strip() else "Нет ответа"
    return fit_button_text(f"{sort_order} · {status}")


def parse_exam_task_button(text: str | None) -> int | None:
    raw = (text or "").strip()
    match = re.fullmatch(r"(\d+)\s*[·•.]\s*(Нет ответа|ответ отправлен)", raw)
    if not match:
        return None
    return int(match.group(1))


def exam_reply_keyboard(answers, *, admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard: list[list[KeyboardButton]] = []
    for item in answers:
        keyboard.append(
            [
                KeyboardButton(
                    text=exam_task_button_text(item.sort_order, item.submitted)
                )
            ]
        )
    keyboard.append([KeyboardButton(text=BTN_EXAM_FINISH)])
    keyboard.append(
        [KeyboardButton(text=BTN_BACK), KeyboardButton(text=BTN_HOME)]
    )
    if admin:
        keyboard.append([KeyboardButton(text=BTN_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def exam_result_keyboard(
    attempt_id: int, answers, *, expanded: int = 0
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for item in answers:
        if item.is_correct:
            status = "верно"
        elif (item.submitted or "").strip():
            status = "неверно"
        else:
            status = "нет ответа"
        mark = "▾" if item.sort_order == expanded else "▸"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=fit_button_text(f"{mark} {item.sort_order}. {status}"),
                    callback_data=MenuCB(
                        a="dq", t=attempt_id, i=item.sort_order
                    ).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def exam_details_keyboard(attempt_id: int, answers) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for item in answers:
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"Задание {item.sort_order}",
                    callback_data=MenuCB(
                        a="dq", t=attempt_id, i=item.sort_order
                    ).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def history_keyboard(topic_id: int, attempts) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []
    for index, attempt in enumerate(attempts, start=1):
        label = f"{index}. {attempt.grade or '—'} · {attempt.correct_count or 0}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=MenuCB(a="dt", t=attempt.id).pack(),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Изменить класс/предмет",
                    callback_data=MenuCB(a="sc").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Подписка",
                    callback_data=MenuCB(a="sb", i=1).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Оставить обращение",
                    callback_data=MenuCB(a="sb", i=2).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Расписание",
                    callback_data=MenuCB(a="sb", i=3).pack(),
                )
            ],
        ]
    )


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
        builder.button(
            text=fit_button_text(topic.title),
            callback_data=TopicCB(action="open", topic_id=topic.id),
        )
        builder.button(
            text=progress_label(progress),
            callback_data=TopicCB(action="open", topic_id=topic.id),
        )
    builder.adjust(1, 1)
    return builder.as_markup()


def theory_keyboard(*, has_more: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Всё ещё непонятно",
                callback_data=LearnCB(action="theory_more").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="К тренировке",
                callback_data=LearnCB(action="training").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="К проверочной",
                callback_data=LearnCB(action="assessment").pack(),
            )
        ],
    ]
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


def after_correct_training_keyboard(
    *, can_level_up: bool, can_level_down: bool = False
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Решить ещё", callback_data=LearnCB(action="more").pack()
            )
        ]
    ]
    level_row: list[InlineKeyboardButton] = []
    if can_level_down:
        level_row.append(
            InlineKeyboardButton(
                text="Снизить сложность",
                callback_data=LearnCB(action="level_down").pack(),
            )
        )
    if can_level_up:
        level_row.append(
            InlineKeyboardButton(
                text="Повысить уровень",
                callback_data=LearnCB(action="level_up").pack(),
            )
        )
    if level_row:
        rows.append(level_row)
    rows.append(
        [
            InlineKeyboardButton(
                text="К проверочной",
                callback_data=LearnCB(action="assessment").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
        builder.button(
            text=fit_button_text(title),
            callback_data=AdminCB(a=action, i=item_id),
        )
    builder.adjust(1)
    return builder.as_markup()


def numbered_pick_keyboard(
    action: str,
    items: list[tuple[int, str]],
    *,
    numbers: list[int] | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    catalog = topics_catalog_html(
        [
            ((numbers[index] if numbers else index + 1), title, None)
            for index, (_, title) in enumerate(items)
        ]
    )
    numbered = [
        (
            item_id,
            f"{(numbers[index] if numbers else index + 1)} · выбрать",
        )
        for index, (item_id, _) in enumerate(items)
    ]
    return catalog, admin_pick_keyboard(action, numbered)


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

