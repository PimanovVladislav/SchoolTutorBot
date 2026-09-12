from __future__ import annotations

import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")

GRADE_RANK = {
    None: -1,
    "не сдано": 0,
    "3": 1,
    "4": 2,
    "5": 3,
    "5+": 4,
}


def assessment_size(required: int | None, available: int) -> int:
    if available <= 0:
        return 0
    want = int(required or available)
    return max(1, min(want, available))


def pass_minimum(total: int) -> int:
    if total <= 0:
        return 0
    return math.ceil(total * 0.5)


def grade_bands(total: int) -> dict[str, tuple[int, int]]:
    """Пороги как в примере на 10 заданий: 3=5–6, 4=7–8, 5=9–10."""
    if total <= 0:
        return {}
    t3 = math.ceil(total * 0.5)
    t4 = math.ceil(total * 0.7)
    t5 = math.ceil(total * 0.9)
    t4 = min(max(t4, t3), total)
    t5 = min(max(t5, t4), total)
    end3 = max(t3, t4 - 1)
    end4 = max(t4, t5 - 1)
    return {
        "3": (t3, end3),
        "4": (t4, end4),
        "5": (t5, total),
    }


def format_span(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}–{end}"


def score_to_grade(correct: int, total: int, *, max_streak: int = 0) -> str:
    if total <= 0 or correct < pass_minimum(total):
        return "не сдано"
    bands = grade_bands(total)
    low5, _ = bands["5"]
    if correct == total and max_streak >= 3:
        return "5+"
    if correct >= low5:
        return "5"
    low4, _ = bands["4"]
    if correct >= low4:
        return "4"
    return "3"


def is_passed(grade: str | None) -> bool:
    return GRADE_RANK.get(grade, -1) >= GRADE_RANK["3"]


def better_grade(current: str | None, incoming: str | None) -> str | None:
    if GRADE_RANK.get(incoming, -1) > GRADE_RANK.get(current, -1):
        return incoming
    return current


def exam_rules_text(title: str, total: int, hours: int = 24) -> str:
    need = pass_minimum(total)
    bands = grade_bands(total)
    day_label = "1 день" if hours % 24 == 0 and hours // 24 == 1 else f"{hours} ч."
    lines = [
        f'Проверочная работа по теме «{title}»',
        f"Работа состоит из {total} заданий, решать их можно в любом порядке.",
        f"Время на выполнение: {day_label}",
        f"Для успешной сдачи необходимо верно решить как минимум {need} заданий.",
        "Система оценивания:",
        f'    Оценка «3»: {format_span(*bands["3"])} верных ответов',
        f'    Оценка «4»: {format_span(*bands["4"])} верных ответов',
        f'    Оценка «5»: {format_span(*bands["5"])} верных ответов',
        '    Оценка «5+»: сдать проверочную трижды на максимальный балл',
    ]
    return "\n".join(lines)


def format_dt(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(MOSCOW).strftime("%d.%m.%Y %H:%M")
