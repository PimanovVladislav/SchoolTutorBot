from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.db import repos
from tutor_bot.db.models import Problem, Topic
from tutor_bot.services.scoring import mastery_from_score, percent, problem_points


async def build_start_queue(
    session: AsyncSession,
    user_id: int,
    topic: Topic,
    include_reinforcement: bool,
) -> list[int]:
    """Очередь закрепления: id задач из ранее пройденных тем."""
    if not include_reinforcement or topic.track_id is None:
        return []
    problems = await repos.list_reinforcement_for_user(
        session, user_id, topic.track_id, topic.grade, topic.id
    )
    # Не больше двух закреплений за раз, чтобы не перегружать урок.
    return [p.id for p in problems[:2]]


async def load_kind_queue(
    session: AsyncSession, topic_id: int, kind: str
) -> list[int]:
    problems = await repos.list_problems(session, topic_id, kind)
    return [p.id for p in problems]


async def apply_assessment_score(
    session: AsyncSession,
    user_id: int,
    topic_id: int,
    problems: list[Problem],
    attempts,
) -> float:
    total = len(problems)
    points = sum(problem_points(p, list(attempts)) for p in problems)
    score = percent(points, total)
    progress = await repos.get_or_create_progress(session, user_id, topic_id)
    progress.assessment_score = score
    progress.mastery = mastery_from_score(score)
    return score


async def apply_reinforcement_result(
    session: AsyncSession,
    user_id: int,
    problem: Problem,
    is_correct: bool,
) -> None:
    source_id = problem.source_topic_id or problem.topic_id
    progress = await repos.get_or_create_progress(session, user_id, source_id)
    progress.reinforcement_total += 1
    if is_correct:
        progress.reinforcement_correct += 1
