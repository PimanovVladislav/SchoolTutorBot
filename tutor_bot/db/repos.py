from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tutor_bot.db.models import (
    Attempt,
    LearningSession,
    Problem,
    Subject,
    Subscription,
    Topic,
    TopicProgress,
    Track,
    User,
)


async def upsert_user(
    session: AsyncSession,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    last_name: Optional[str],
    role: str = "student",
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
        )
        session.add(user)
        await session.flush()
        return user
    user.username = username
    user.first_name = first_name
    user.last_name = last_name
    if role == "admin":
        user.role = "admin"
    return user


async def get_user(session: AsyncSession, user_id: int) -> Optional[User]:
    return await session.get(User, user_id)


async def set_user_grade_and_track(
    session: AsyncSession, user_id: int, grade: int, track_id: int
) -> None:
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(grade=grade, track_id=track_id)
    )


async def set_current_topic(
    session: AsyncSession, user_id: int, topic_id: Optional[int]
) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(current_topic_id=topic_id)
    )


async def get_active_subscription(
    session: AsyncSession, user_id: int, now: datetime
) -> Optional[Subscription]:
    stmt: Select[tuple[Subscription]] = (
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.ends_at > now,
        )
        .order_by(Subscription.ends_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def grant_subscription(
    session: AsyncSession,
    user_id: int,
    days: int,
    source: str,
    now: datetime,
    payment_id: Optional[str] = None,
) -> Subscription:
    current = await get_active_subscription(session, user_id, now)
    start = now
    end_base = current.ends_at if current else now
    if current:
        current.status = "superseded"
        end_base = max(current.ends_at, now)
    sub = Subscription(
        user_id=user_id,
        starts_at=start,
        ends_at=end_base + timedelta(days=days),
        status="active",
        source=source,
        provider_payment_id=payment_id,
    )
    session.add(sub)
    await session.flush()
    return sub


async def revoke_subscriptions(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(Subscription)
        .where(Subscription.user_id == user_id, Subscription.status == "active")
        .values(status="revoked")
    )


async def get_subject_by_slug(session: AsyncSession, slug: str) -> Optional[Subject]:
    stmt = select(Subject).where(Subject.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_track_by_slug(
    session: AsyncSession, subject_id: int, slug: str
) -> Optional[Track]:
    stmt = select(Track).where(Track.subject_id == subject_id, Track.slug == slug)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_topics_for_grade(
    session: AsyncSession, track_id: int, grade: int
) -> Sequence[Topic]:
    stmt = (
        select(Topic)
        .where(Topic.track_id == track_id, Topic.grade == grade)
        .order_by(Topic.sort_order, Topic.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_topic(session: AsyncSession, topic_id: int) -> Optional[Topic]:
    return await session.get(Topic, topic_id)


async def list_problems(
    session: AsyncSession, topic_id: int, kind: str
) -> Sequence[Problem]:
    stmt = (
        select(Problem)
        .where(Problem.topic_id == topic_id, Problem.kind == kind)
        .order_by(Problem.sort_order, Problem.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_problem(session: AsyncSession, problem_id: int) -> Optional[Problem]:
    return await session.get(Problem, problem_id)


async def list_reinforcement_for_user(
    session: AsyncSession, user_id: int, track_id: int, grade: int, current_topic_id: int
) -> list[Problem]:
    """Задачи из уже пройденных тем того же класса — для закрепления перед новой темой."""
    progress_stmt = select(TopicProgress.topic_id).where(
        TopicProgress.user_id == user_id,
        TopicProgress.assessment_score.is_not(None),
        TopicProgress.topic_id != current_topic_id,
    )
    done_ids = set((await session.execute(progress_stmt)).scalars().all())
    if not done_ids:
        return []

    stmt = (
        select(Problem)
        .join(Topic, Topic.id == Problem.topic_id)
        .where(
            Problem.kind == "reinforcement",
            Topic.track_id == track_id,
            Topic.grade == grade,
            Problem.topic_id.in_(done_ids),
        )
        .order_by(Topic.sort_order, Problem.sort_order)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_session(
    session: AsyncSession, user_id: int, topic_id: int, stage: str
) -> LearningSession:
    await session.execute(
        update(LearningSession)
        .where(
            LearningSession.user_id == user_id,
            LearningSession.status == "active",
        )
        .values(status="abandoned", finished_at=datetime.utcnow())
    )
    item = LearningSession(
        user_id=user_id, topic_id=topic_id, stage=stage, status="active"
    )
    session.add(item)
    await session.flush()
    return item


async def get_active_session(
    session: AsyncSession, user_id: int
) -> Optional[LearningSession]:
    stmt = (
        select(LearningSession)
        .where(LearningSession.user_id == user_id, LearningSession.status == "active")
        .order_by(LearningSession.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def finish_session(session: AsyncSession, session_id: int) -> None:
    await session.execute(
        update(LearningSession)
        .where(LearningSession.id == session_id)
        .values(status="finished", finished_at=datetime.utcnow())
    )


async def set_session_stage(
    session: AsyncSession, session_id: int, stage: str
) -> None:
    await session.execute(
        update(LearningSession)
        .where(LearningSession.id == session_id)
        .values(stage=stage)
    )


async def add_attempt(
    session: AsyncSession,
    user_id: int,
    session_id: int,
    problem_id: int,
    submitted: str,
    is_correct: bool,
    used_help: bool,
) -> Attempt:
    item = Attempt(
        user_id=user_id,
        session_id=session_id,
        problem_id=problem_id,
        submitted=submitted[:255],
        is_correct=is_correct,
        used_help=used_help,
    )
    session.add(item)
    await session.flush()
    return item


async def list_session_attempts(
    session: AsyncSession, session_id: int
) -> Sequence[Attempt]:
    stmt = (
        select(Attempt)
        .where(Attempt.session_id == session_id)
        .order_by(Attempt.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_or_create_progress(
    session: AsyncSession, user_id: int, topic_id: int
) -> TopicProgress:
    stmt = select(TopicProgress).where(
        TopicProgress.user_id == user_id, TopicProgress.topic_id == topic_id
    )
    progress = (await session.execute(stmt)).scalar_one_or_none()
    if progress is None:
        progress = TopicProgress(user_id=user_id, topic_id=topic_id)
        session.add(progress)
        await session.flush()
    return progress


async def list_progress_with_topics(
    session: AsyncSession, user_id: int, track_id: int, grade: int
) -> list[tuple[Topic, Optional[TopicProgress]]]:
    topics = await list_topics_for_grade(session, track_id, grade)
    if not topics:
        return []
    stmt = select(TopicProgress).where(
        TopicProgress.user_id == user_id,
        TopicProgress.topic_id.in_([t.id for t in topics]),
    )
    progress_rows = (await session.execute(stmt)).scalars().all()
    by_topic = {p.topic_id: p for p in progress_rows}
    return [(topic, by_topic.get(topic.id)) for topic in topics]


async def count_users(session: AsyncSession) -> int:
    from sqlalchemy import func as sa_func

    return int((await session.execute(select(sa_func.count(User.id)))).scalar_one())


async def get_math_school_track(session: AsyncSession) -> Optional[Track]:
    stmt = (
        select(Track)
        .join(Subject)
        .where(Subject.slug == "math", Track.slug == "school")
        .options(selectinload(Track.subject))
    )
    return (await session.execute(stmt)).scalar_one_or_none()
