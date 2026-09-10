from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tutor_bot.content.math_school import MATH_SCHOOL_TOPICS
from tutor_bot.db import repos
from tutor_bot.db.models import GradeOption, Problem, Subject, Topic, Track


async def seed_curriculum(session: AsyncSession) -> None:
    await _ensure_grades(session)
    subject = await _get_or_create_subject(session)
    track = await _get_or_create_track(session, subject.id)
    for spec in MATH_SCHOOL_TOPICS:
        topic = await _upsert_topic(session, track.id, spec)
        await _upsert_theories(session, topic, spec)
        await _replace_problems(session, topic.id, spec["problems"])


async def _ensure_grades(session: AsyncSession) -> None:
    for grade in (6, 7, 8, 9):
        if await session.get(GradeOption, grade) is None:
            session.add(GradeOption(grade=grade))
    await session.flush()


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
            theory=spec.get("theory") or "",
            theory_kind=spec.get("theory_kind", "text"),
            theory_image_path=spec.get("theory_image_path"),
            assessment_required=int(spec.get("assessment_required", 3)),
            sort_order=spec["sort_order"],
        )
        session.add(topic)
        await session.flush()
        return topic
    topic.title = spec["title"]
    topic.summary = spec["summary"]
    topic.theory = spec.get("theory") or ""
    topic.theory_kind = spec.get("theory_kind", "text")
    topic.theory_image_path = spec.get("theory_image_path")
    topic.assessment_required = int(spec.get("assessment_required", 3))
    topic.sort_order = spec["sort_order"]
    return topic


def _theory_specs(spec: dict) -> list[dict]:
    if spec.get("theories"):
        return list(spec["theories"])
    if spec.get("theory") or spec.get("theory_image_path"):
        return [
            {
                "kind": spec.get("theory_kind", "text"),
                "body": spec.get("theory") or "",
                "image_path": spec.get("theory_image_path"),
            }
        ]
    return []


def _text_list(spec: dict, plural: str, singular: str) -> list[str]:
    if spec.get(plural):
        return [item for item in spec[plural] if item]
    if spec.get(singular):
        return [spec[singular]]
    return []


async def _upsert_theories(session: AsyncSession, topic: Topic, spec: dict) -> None:
    for index, item in enumerate(_theory_specs(spec), start=1):
        await repos.upsert_topic_theory(
            session,
            topic.id,
            index,
            body=item.get("body") or "",
            kind=item.get("kind") or "text",
            image_path=item.get("image_path"),
        )


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
        if spec["kind"] == "training":
            default_difficulty = ((spec["sort_order"] - 1) % 3) + 1
        else:
            default_difficulty = 2
        problem.difficulty = int(spec.get("difficulty", default_difficulty))
        if problem.difficulty < 1:
            problem.difficulty = 1
        problem.source_topic_id = topic_id
        await session.flush()
        hints = _text_list(spec, "hints", "hint")
        solutions = _text_list(spec, "solutions", "solution")
        for index, body in enumerate(hints, start=1):
            await repos.upsert_problem_hint(session, problem.id, index, body)
        for index, body in enumerate(solutions, start=1):
            await repos.upsert_problem_solution(session, problem.id, index, body)
