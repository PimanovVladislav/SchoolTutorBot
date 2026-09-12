from __future__ import annotations

import random

from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.db import repos
from tutor_bot.db.models import Problem, Topic
from tutor_bot.services.grades import assessment_size
from tutor_bot.services.scoring import mastery_from_score, percent, problem_points


async def build_start_queue(
    session: AsyncSession,
    user_id: int,
    topic: Topic,
    include_reinforcement: bool,
) -> list[int]:
    if not include_reinforcement or topic.track_id is None:
        return []
    problems = await repos.list_reinforcement_for_user(
        session, user_id, topic.track_id, topic.grade, topic.id
    )
    if not problems:
        return []
    sample = problems[:]
    random.shuffle(sample)
    return [p.id for p in sample[:2]]


async def pick_assessment_queue(
    session: AsyncSession,
    topic: Topic,
    *,
    avoid_ids: list[int] | None = None,
) -> list[int]:
    problems = list(await repos.list_problems(session, topic.id, "assessment"))
    if not problems:
        return []
    count = assessment_size(topic.assessment_required, len(problems))
    if count <= 0:
        return []
    avoid = set(avoid_ids or [])
    pool = [item for item in problems if item.id not in avoid]
    if len(pool) < count:
        pool = problems
    chosen = random.sample(pool, count)
    random.shuffle(chosen)
    return [item.id for item in chosen]


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
