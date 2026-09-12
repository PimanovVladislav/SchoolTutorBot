from datetime import datetime, timedelta
from typing import Optional, Sequence

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tutor_bot.db.models import (
    AssessmentAnswer,
    AssessmentAttempt,
    Attempt,
    GradeOption,
    LearningSession,
    Problem,
    ProblemHint,
    ProblemSolution,
    Subject,
    Subscription,
    Topic,
    TopicProgress,
    TopicTheory,
    Track,
    User,
    UserProblemStat,
)
from tutor_bot.services.topics import plan_topic_insert


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
        await session.refresh(user)
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


async def get_topic_by_number(
    session: AsyncSession, track_id: int, grade: int, number: int
) -> Optional[Topic]:
    stmt = (
        select(Topic)
        .where(
            Topic.track_id == track_id,
            Topic.grade == grade,
            Topic.sort_order == number,
        )
        .order_by(Topic.id)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_problems(
    session: AsyncSession, topic_id: int, kind: str
) -> Sequence[Problem]:
    stmt = (
        select(Problem)
        .where(Problem.topic_id == topic_id, Problem.kind == kind)
        .order_by(Problem.difficulty, Problem.sort_order, Problem.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_problems_by_ids(
    session: AsyncSession, problem_ids: list[int]
) -> list[Problem]:
    if not problem_ids:
        return []
    stmt = select(Problem).where(Problem.id.in_(problem_ids))
    found = {p.id: p for p in (await session.execute(stmt)).scalars().all()}
    return [found[pid] for pid in problem_ids if pid in found]


async def list_difficulties(
    session: AsyncSession, topic_id: int, kind: str
) -> list[int]:
    stmt = (
        select(Problem.difficulty)
        .where(Problem.topic_id == topic_id, Problem.kind == kind)
        .distinct()
        .order_by(Problem.difficulty)
    )
    return [int(value) for value in (await session.execute(stmt)).scalars().all()]


async def pick_random_problem(
    session: AsyncSession,
    topic_id: int,
    kind: str,
    *,
    difficulty: Optional[int] = None,
    exclude_ids: Optional[list[int]] = None,
) -> Optional[Problem]:
    filters = [Problem.topic_id == topic_id, Problem.kind == kind]
    if difficulty is not None:
        filters.append(Problem.difficulty == difficulty)
    excluded = [pid for pid in (exclude_ids or []) if pid]
    stmt = select(Problem).where(*filters)
    if excluded:
        stmt = stmt.where(Problem.id.not_in(excluded))
    return (
        await session.execute(stmt.order_by(func.rand()).limit(1))
    ).scalar_one_or_none()


async def pick_training_problem(
    session: AsyncSession,
    user_id: int,
    topic_id: int,
    difficulty: int,
    *,
    exclude_ids: Optional[list[int]] = None,
    cooldown_days: int = 7,
) -> Optional[Problem]:
    cutoff = datetime.utcnow() - timedelta(days=cooldown_days)
    excluded = [pid for pid in (exclude_ids or []) if pid]
    filters = [
        Problem.topic_id == topic_id,
        Problem.kind == "training",
        Problem.difficulty == difficulty,
        or_(
            UserProblemStat.last_solved_at.is_(None),
            UserProblemStat.last_solved_at <= cutoff,
        ),
    ]
    stmt = (
        select(Problem)
        .outerjoin(
            UserProblemStat,
            (UserProblemStat.problem_id == Problem.id)
            & (UserProblemStat.user_id == user_id),
        )
        .where(*filters)
    )
    if excluded:
        stmt = stmt.where(Problem.id.not_in(excluded))
    return (
        await session.execute(stmt.order_by(func.rand()).limit(1))
    ).scalar_one_or_none()


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


async def list_user_ids(session: AsyncSession) -> list[int]:
    return list((await session.execute(select(User.id))).scalars().all())


async def list_users_page(
    session: AsyncSession, offset: int = 0, limit: int = 6
) -> Sequence[User]:
    stmt = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    clean = username.strip().lstrip("@")
    stmt = select(User).where(func.lower(User.username) == clean.lower())
    return (await session.execute(stmt)).scalar_one_or_none()


async def find_user(session: AsyncSession, raw: str) -> Optional[User]:
    text = raw.strip()
    if text.startswith("@"):
        return await get_user_by_username(session, text)
    if text.isdigit():
        return await get_user(session, int(text))
    return await get_user_by_username(session, text)


async def list_grades(session: AsyncSession) -> list[int]:
    stored = list(
        (await session.execute(select(GradeOption.grade).order_by(GradeOption.grade)))
        .scalars()
        .all()
    )
    if stored:
        return [int(g) for g in stored]
    from_topics = list(
        (
            await session.execute(
                select(Topic.grade).distinct().order_by(Topic.grade)
            )
        )
        .scalars()
        .all()
    )
    return [int(g) for g in from_topics] or [6, 7, 8, 9]


async def add_grade(session: AsyncSession, grade: int) -> GradeOption:
    existing = await session.get(GradeOption, grade)
    if existing:
        return existing
    item = GradeOption(grade=grade)
    session.add(item)
    await session.flush()
    return item


async def list_subjects(session: AsyncSession) -> Sequence[Subject]:
    stmt = select(Subject).where(Subject.is_active.is_(True)).order_by(Subject.id)
    return (await session.execute(stmt)).scalars().all()


async def create_subject(session: AsyncSession, title: str) -> Subject:
    slug = f"subj-{int(datetime.utcnow().timestamp())}"
    item = Subject(slug=slug, title=title.strip(), is_active=True)
    session.add(item)
    await session.flush()
    track = Track(subject_id=item.id, slug="school", title="Школьная программа")
    session.add(track)
    await session.flush()
    return item


async def default_track_for_subject(
    session: AsyncSession, subject_id: int
) -> Optional[Track]:
    stmt = (
        select(Track)
        .where(Track.subject_id == subject_id)
        .order_by(Track.id)
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def allocate_topic_number(
    session: AsyncSession,
    track_id: int,
    grade: int,
    requested: int | None,
) -> int:
    topics = list(await list_topics_for_grade(session, track_id, grade))
    number, shifted = plan_topic_insert(
        [item.sort_order for item in topics], requested
    )
    for topic, new_order in reversed(list(zip(topics, shifted))):
        if topic.sort_order != new_order:
            topic.sort_order = new_order
    await session.flush()
    return number


async def create_topic(
    session: AsyncSession,
    *,
    track_id: int,
    grade: int,
    title: str,
    summary: str,
    theory: str,
    theory_kind: str,
    theory_image_path: Optional[str],
    assessment_required: int,
    number: Optional[int] = None,
) -> Topic:
    slug = f"t-{int(datetime.utcnow().timestamp())}"
    sort_order = await allocate_topic_number(session, track_id, grade, number)
    item = Topic(
        track_id=track_id,
        grade=grade,
        slug=slug,
        title=title.strip(),
        summary=summary.strip(),
        theory=theory,
        theory_kind=theory_kind,
        theory_image_path=theory_image_path,
        assessment_required=max(1, assessment_required),
        sort_order=sort_order,
    )
    session.add(item)
    await session.flush()
    if theory or theory_image_path:
        await add_topic_theory(
            session,
            item.id,
            body=theory or "",
            kind=theory_kind,
            image_path=theory_image_path,
        )
    return item


async def next_problem_sort(session: AsyncSession, topic_id: int, kind: str) -> int:
    max_order = (
        await session.execute(
            select(func.max(Problem.sort_order)).where(
                Problem.topic_id == topic_id, Problem.kind == kind
            )
        )
    ).scalar_one()
    return (max_order or 0) + 1


async def create_problem(
    session: AsyncSession,
    *,
    topic_id: int,
    kind: str,
    difficulty: int,
    prompt: str,
    correct_answer: str,
    hint: str,
    solution: str,
    answer_type: str = "text",
    hints: Optional[list[str]] = None,
    solutions: Optional[list[str]] = None,
) -> Problem:
    item = Problem(
        topic_id=topic_id,
        source_topic_id=topic_id,
        kind=kind,
        answer_type=answer_type,
        prompt=prompt,
        correct_answer=correct_answer.strip(),
        hint=hint,
        solution=solution,
        difficulty=difficulty,
        sort_order=await next_problem_sort(session, topic_id, kind),
    )
    session.add(item)
    await session.flush()
    hint_list = [h for h in (hints if hints is not None else ([hint] if hint else [])) if h]
    sol_list = [
        s for s in (solutions if solutions is not None else ([solution] if solution else [])) if s
    ]
    item.hint = hint_list[0] if hint_list else ""
    item.solution = sol_list[0] if sol_list else ""
    for body in hint_list:
        await add_problem_hint(session, item.id, body)
    for body in sol_list:
        await add_problem_solution(session, item.id, body)
    return item


async def flag_problem(session: AsyncSession, problem_id: int) -> Optional[Problem]:
    problem = await session.get(Problem, problem_id)
    if problem is None:
        return None
    problem.needs_review = True
    return problem


async def clear_problem_flag(session: AsyncSession, problem_id: int) -> None:
    problem = await session.get(Problem, problem_id)
    if problem is not None:
        problem.needs_review = False


async def list_flagged_problems(session: AsyncSession) -> Sequence[Problem]:
    stmt = (
        select(Problem)
        .where(Problem.needs_review.is_(True))
        .order_by(Problem.id.desc())
        .limit(30)
    )
    return (await session.execute(stmt)).scalars().all()


async def touch_problem_stat(
    session: AsyncSession, user_id: int, problem_id: int, *, solved: bool
) -> None:
    stmt = select(UserProblemStat).where(
        UserProblemStat.user_id == user_id,
        UserProblemStat.problem_id == problem_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    now = datetime.utcnow()
    if row is None:
        row = UserProblemStat(
            user_id=user_id,
            problem_id=problem_id,
            last_attempt_at=now,
            last_solved_at=now if solved else None,
        )
        session.add(row)
        await session.flush()
        return
    row.last_attempt_at = now
    if solved:
        row.last_solved_at = now


async def list_topic_theories(
    session: AsyncSession, topic_id: int
) -> Sequence[TopicTheory]:
    stmt = (
        select(TopicTheory)
        .where(TopicTheory.topic_id == topic_id)
        .order_by(TopicTheory.edition, TopicTheory.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_topic_theory(
    session: AsyncSession, topic_id: int, edition: int
) -> Optional[TopicTheory]:
    stmt = select(TopicTheory).where(
        TopicTheory.topic_id == topic_id, TopicTheory.edition == edition
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def refresh_topic_theory_counts(session: AsyncSession, topic_id: int) -> int:
    total = int(
        (
            await session.execute(
                select(func.count()).select_from(TopicTheory).where(
                    TopicTheory.topic_id == topic_id
                )
            )
        ).scalar_one()
        or 0
    )
    if total:
        await session.execute(
            update(TopicTheory)
            .where(TopicTheory.topic_id == topic_id)
            .values(edition_count=total)
        )
    return total


async def add_topic_theory(
    session: AsyncSession,
    topic_id: int,
    *,
    body: str,
    kind: str = "text",
    image_path: Optional[str] = None,
) -> TopicTheory:
    max_edition = (
        await session.execute(
            select(func.max(TopicTheory.edition)).where(TopicTheory.topic_id == topic_id)
        )
    ).scalar_one()
    edition = int(max_edition or 0) + 1
    row = TopicTheory(
        topic_id=topic_id,
        edition=edition,
        edition_count=edition,
        body=body or "",
        kind=kind or "text",
        image_path=image_path,
    )
    session.add(row)
    await session.flush()
    row.edition_count = await refresh_topic_theory_counts(session, topic_id)
    if edition == 1:
        topic = await session.get(Topic, topic_id)
        if topic is not None:
            topic.theory = body or ""
            topic.theory_kind = kind or "text"
            topic.theory_image_path = image_path
    return row


async def upsert_topic_theory(
    session: AsyncSession,
    topic_id: int,
    edition: int,
    *,
    body: str,
    kind: str = "text",
    image_path: Optional[str] = None,
) -> TopicTheory:
    row = await get_topic_theory(session, topic_id, edition)
    if row is None:
        row = TopicTheory(topic_id=topic_id, edition=edition)
        session.add(row)
    row.body = body or ""
    row.kind = kind or "text"
    row.image_path = image_path
    await session.flush()
    await refresh_topic_theory_counts(session, topic_id)
    if edition == 1:
        topic = await session.get(Topic, topic_id)
        if topic is not None:
            topic.theory = body or ""
            topic.theory_kind = kind or "text"
            topic.theory_image_path = image_path
    return row


async def list_topic_problems(
    session: AsyncSession, topic_id: int
) -> Sequence[Problem]:
    stmt = (
        select(Problem)
        .where(Problem.topic_id == topic_id)
        .order_by(Problem.kind, Problem.sort_order, Problem.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def _refresh_parent_counts(session: AsyncSession, model, parent_col, parent_id: int) -> int:
    total = int(
        (
            await session.execute(
                select(func.count()).select_from(model).where(parent_col == parent_id)
            )
        ).scalar_one()
        or 0
    )
    if total:
        await session.execute(
            update(model).where(parent_col == parent_id).values(edition_count=total)
        )
    return total


async def list_problem_hints(
    session: AsyncSession, problem_id: int
) -> Sequence[ProblemHint]:
    stmt = (
        select(ProblemHint)
        .where(ProblemHint.problem_id == problem_id)
        .order_by(ProblemHint.edition, ProblemHint.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def list_problem_solutions(
    session: AsyncSession, problem_id: int
) -> Sequence[ProblemSolution]:
    stmt = (
        select(ProblemSolution)
        .where(ProblemSolution.problem_id == problem_id)
        .order_by(ProblemSolution.edition, ProblemSolution.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def list_hint_bodies(session: AsyncSession, problem: Problem) -> list[str]:
    rows = await list_problem_hints(session, problem.id)
    if rows:
        return [row.body for row in rows if row.body]
    return [problem.hint] if problem.hint else []


async def list_solution_bodies(session: AsyncSession, problem: Problem) -> list[str]:
    rows = await list_problem_solutions(session, problem.id)
    if rows:
        return [row.body for row in rows if row.body]
    return [problem.solution] if problem.solution else []


async def add_problem_hint(
    session: AsyncSession, problem_id: int, body: str
) -> ProblemHint:
    max_edition = (
        await session.execute(
            select(func.max(ProblemHint.edition)).where(
                ProblemHint.problem_id == problem_id
            )
        )
    ).scalar_one()
    edition = int(max_edition or 0) + 1
    row = ProblemHint(
        problem_id=problem_id,
        edition=edition,
        edition_count=edition,
        body=body,
    )
    session.add(row)
    await session.flush()
    row.edition_count = await _refresh_parent_counts(
        session, ProblemHint, ProblemHint.problem_id, problem_id
    )
    if edition == 1:
        problem = await session.get(Problem, problem_id)
        if problem is not None:
            problem.hint = body
    return row


async def add_problem_solution(
    session: AsyncSession, problem_id: int, body: str
) -> ProblemSolution:
    max_edition = (
        await session.execute(
            select(func.max(ProblemSolution.edition)).where(
                ProblemSolution.problem_id == problem_id
            )
        )
    ).scalar_one()
    edition = int(max_edition or 0) + 1
    row = ProblemSolution(
        problem_id=problem_id,
        edition=edition,
        edition_count=edition,
        body=body,
    )
    session.add(row)
    await session.flush()
    row.edition_count = await _refresh_parent_counts(
        session, ProblemSolution, ProblemSolution.problem_id, problem_id
    )
    if edition == 1:
        problem = await session.get(Problem, problem_id)
        if problem is not None:
            problem.solution = body
    return row


async def upsert_problem_hint(
    session: AsyncSession, problem_id: int, edition: int, body: str
) -> ProblemHint:
    stmt = select(ProblemHint).where(
        ProblemHint.problem_id == problem_id, ProblemHint.edition == edition
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = ProblemHint(problem_id=problem_id, edition=edition)
        session.add(row)
    row.body = body
    await session.flush()
    await _refresh_parent_counts(
        session, ProblemHint, ProblemHint.problem_id, problem_id
    )
    if edition == 1:
        problem = await session.get(Problem, problem_id)
        if problem is not None:
            problem.hint = body
    return row


async def upsert_problem_solution(
    session: AsyncSession, problem_id: int, edition: int, body: str
) -> ProblemSolution:
    stmt = select(ProblemSolution).where(
        ProblemSolution.problem_id == problem_id, ProblemSolution.edition == edition
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        row = ProblemSolution(problem_id=problem_id, edition=edition)
        session.add(row)
    row.body = body
    await session.flush()
    await _refresh_parent_counts(
        session, ProblemSolution, ProblemSolution.problem_id, problem_id
    )
    if edition == 1:
        problem = await session.get(Problem, problem_id)
        if problem is not None:
            problem.solution = body
    return row


def parse_id_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(part) for part in raw.split(",") if part.strip().isdigit()]


def join_id_list(ids: list[int]) -> str:
    return ",".join(str(item) for item in ids)


async def get_active_attempt(
    session: AsyncSession, user_id: int, topic_id: int
) -> Optional[AssessmentAttempt]:
    stmt = (
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.topic_id == topic_id,
            AssessmentAttempt.status == "in_progress",
        )
        .order_by(AssessmentAttempt.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_attempt(
    session: AsyncSession, attempt_id: int
) -> Optional[AssessmentAttempt]:
    return await session.get(AssessmentAttempt, attempt_id)


async def list_topic_attempts(
    session: AsyncSession, user_id: int, topic_id: int
) -> Sequence[AssessmentAttempt]:
    stmt = (
        select(AssessmentAttempt)
        .where(
            AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.topic_id == topic_id,
            AssessmentAttempt.status.in_(("completed", "expired")),
        )
        .order_by(AssessmentAttempt.started_at.asc(), AssessmentAttempt.id.asc())
    )
    return (await session.execute(stmt)).scalars().all()


async def list_attempts_for_topics(
    session: AsyncSession, user_id: int, topic_ids: list[int]
) -> Sequence[AssessmentAttempt]:
    if not topic_ids:
        return []
    stmt = select(AssessmentAttempt).where(
        AssessmentAttempt.user_id == user_id,
        AssessmentAttempt.topic_id.in_(topic_ids),
    )
    return (await session.execute(stmt)).scalars().all()


async def count_max_scores(
    session: AsyncSession,
    user_id: int,
    topic_id: int,
    *,
    exclude_id: Optional[int] = None,
) -> int:
    filters = [
        AssessmentAttempt.user_id == user_id,
        AssessmentAttempt.topic_id == topic_id,
        AssessmentAttempt.status.in_(("completed", "expired")),
        AssessmentAttempt.correct_count.is_not(None),
        AssessmentAttempt.correct_count == AssessmentAttempt.total,
        AssessmentAttempt.total > 0,
    ]
    if exclude_id:
        filters.append(AssessmentAttempt.id != exclude_id)
    return int(
        (
            await session.execute(
                select(func.count()).select_from(AssessmentAttempt).where(*filters)
            )
        ).scalar_one()
        or 0
    )


async def create_assessment_attempt(
    session: AsyncSession,
    *,
    user_id: int,
    topic_id: int,
    problem_ids: list[int],
    deadline_at: datetime,
    started_at: datetime,
) -> AssessmentAttempt:
    attempt = AssessmentAttempt(
        user_id=user_id,
        topic_id=topic_id,
        started_at=started_at,
        deadline_at=deadline_at,
        status="in_progress",
        total=len(problem_ids),
        problem_ids=join_id_list(problem_ids),
    )
    session.add(attempt)
    await session.flush()
    for index, problem_id in enumerate(problem_ids, start=1):
        session.add(
            AssessmentAnswer(
                attempt_id=attempt.id,
                problem_id=problem_id,
                sort_order=index,
                submitted="",
            )
        )
    await session.flush()
    return attempt


async def get_attempt_answers(
    session: AsyncSession, attempt_id: int
) -> Sequence[AssessmentAnswer]:
    stmt = (
        select(AssessmentAnswer)
        .where(AssessmentAnswer.attempt_id == attempt_id)
        .order_by(AssessmentAnswer.sort_order, AssessmentAnswer.id)
    )
    return (await session.execute(stmt)).scalars().all()


async def save_attempt_answer(
    session: AsyncSession, attempt_id: int, problem_id: int, submitted: str
) -> Optional[AssessmentAnswer]:
    stmt = select(AssessmentAnswer).where(
        AssessmentAnswer.attempt_id == attempt_id,
        AssessmentAnswer.problem_id == problem_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    row.submitted = submitted
    return row


async def finish_attempt(
    session: AsyncSession,
    attempt: AssessmentAttempt,
    *,
    finished_at: datetime,
    status: str,
    correct_count: int,
    grade: str,
) -> None:
    attempt.finished_at = finished_at
    attempt.status = status
    attempt.correct_count = correct_count
    attempt.grade = grade

