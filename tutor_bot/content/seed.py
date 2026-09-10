from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.content.math_school import MATH_SCHOOL_TOPICS
from tutor_bot.db.models import Problem, Subject, Topic, Track


async def seed_curriculum(session: AsyncSession) -> None:
    subject = await _get_or_create_subject(session)
    track = await _get_or_create_track(session, subject.id)
    for spec in MATH_SCHOOL_TOPICS:
        topic = await _upsert_topic(session, track.id, spec)
        await _replace_problems(session, topic.id, spec["problems"])


async def _get_or_create_subject(session: AsyncSession) -> Subject:
    stmt = select(Subject).where(Subject.slug == "math")
    subject = (await session.execute(stmt)).scalar_one_or_none()
    if subject is None:
        subject = Subject(slug="math", title="Математика", is_active=True)
        session.add(subject)
        await session.flush()
        return subject
    subject.title = "Математика"
    subject.is_active = True
    return subject


async def _get_or_create_track(session: AsyncSession, subject_id: int) -> Track:
    stmt = select(Track).where(Track.subject_id == subject_id, Track.slug == "school")
    track = (await session.execute(stmt)).scalar_one_or_none()
    if track is None:
        track = Track(subject_id=subject_id, slug="school", title="Школьная программа")
        session.add(track)
        await session.flush()
        return track
    track.title = "Школьная программа"
    return track


async def _upsert_topic(session: AsyncSession, track_id: int, spec: dict) -> Topic:
    stmt = select(Topic).where(
        Topic.track_id == track_id,
        Topic.grade == spec["grade"],
        Topic.slug == spec["slug"],
    )
    topic = (await session.execute(stmt)).scalar_one_or_none()
    if topic is None:
        topic = Topic(
            track_id=track_id,
            grade=spec["grade"],
            slug=spec["slug"],
            title=spec["title"],
            summary=spec["summary"],
            theory=spec["theory"],
            sort_order=spec["sort_order"],
        )
        session.add(topic)
        await session.flush()
        return topic
    topic.title = spec["title"]
    topic.summary = spec["summary"]
    topic.theory = spec["theory"]
    topic.sort_order = spec["sort_order"]
    return topic


async def _replace_problems(
    session: AsyncSession, topic_id: int, problems: list[dict]
) -> None:
    existing = (
        await session.execute(select(Problem).where(Problem.topic_id == topic_id))
    ).scalars().all()
    by_key = {(p.kind, p.sort_order): p for p in existing}
    for spec in problems:
        key = (spec["kind"], spec["sort_order"])
        problem = by_key.get(key)
        if problem is None:
            problem = Problem(topic_id=topic_id, source_topic_id=topic_id)
            session.add(problem)
        problem.kind = spec["kind"]
        problem.answer_type = spec["answer_type"]
        problem.prompt = spec["prompt"]
        problem.correct_answer = spec["correct_answer"]
        problem.hint = spec.get("hint", "")
        problem.solution = spec.get("solution", "")
        problem.sort_order = spec["sort_order"]
        problem.source_topic_id = topic_id
