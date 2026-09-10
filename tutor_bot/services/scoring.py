from __future__ import annotations

from tutor_bot.db.models import Attempt, Problem


def problem_points(problem: Problem, attempts: list[Attempt]) -> float:
    """1 — верно без разбора, 0.5 — верно после помощи, 0 — неверно."""
    relevant = [a for a in attempts if a.problem_id == problem.id]
    if not relevant:
        return 0.0
    used_help = any(a.used_help for a in relevant)
    if any(a.is_correct for a in relevant) and not used_help:
        return 1.0
    if any(a.is_correct for a in relevant) and used_help:
        return 0.5
    if used_help:
        return 0.25
    return 0.0


def percent(score: float, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * score / total, 1)


def mastery_from_score(score: float | None) -> str:
    if score is None:
        return "learning"
    if score >= 85:
        return "mastered"
    if score >= 70:
        return "confident"
    if score >= 40:
        return "needs_practice"
    return "learning"


MASTERY_LABELS = {
    "not_started": "ещё не начата",
    "learning": "изучается",
    "needs_practice": "нужна практика",
    "confident": "уверенно",
    "mastered": "тема усвоена",
}
