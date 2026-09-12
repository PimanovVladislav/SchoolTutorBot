from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    track_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tracks.id"), nullable=True
    )
    current_topic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("topics.id"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(32), default="student")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now()
    )

    track: Mapped[Optional["Track"]] = relationship(
        foreign_keys=[track_id], lazy="raise"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        back_populates="user", lazy="raise"
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_user_ends", "user_id", "ends_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="active")
    source: Mapped[str] = mapped_column(String(32), default="admin")
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="subscriptions", lazy="raise")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    tracks: Mapped[list["Track"]] = relationship(
        back_populates="subject", lazy="selectin"
    )


class Track(Base):
    """Направление: школьная программа, ОГЭ, ЕГЭ, доп. образование."""

    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("subject_id", "slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"))
    slug: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))

    subject: Mapped[Subject] = relationship(back_populates="tracks", lazy="selectin")
    topics: Mapped[list["Topic"]] = relationship(back_populates="track", lazy="raise")


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint("track_id", "grade", "slug"),
        Index("ix_topics_track_grade_order", "track_id", "grade", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    grade: Mapped[int] = mapped_column(Integer)
    slug: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(String(512), default="")
    theory: Mapped[str] = mapped_column(Text, default="")
    theory_kind: Mapped[str] = mapped_column(String(16), default="text")
    theory_image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    assessment_required: Mapped[int] = mapped_column(Integer, default=3)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    track: Mapped[Track] = relationship(back_populates="topics", lazy="selectin")
    problems: Mapped[list["Problem"]] = relationship(
        back_populates="topic",
        foreign_keys="Problem.topic_id",
        lazy="raise",
    )
    theories: Mapped[list["TopicTheory"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class Problem(Base):
    __tablename__ = "problems"
    __table_args__ = (Index("ix_problems_topic_kind", "topic_id", "kind", "sort_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    source_topic_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("topics.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))  # training | assessment | reinforcement
    answer_type: Mapped[str] = mapped_column(String(32))
    prompt: Mapped[str] = mapped_column(Text)
    correct_answer: Mapped[str] = mapped_column(String(255))
    choices: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    hint: Mapped[str] = mapped_column(Text, default="")
    solution: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    topic: Mapped[Topic] = relationship(
        foreign_keys=[topic_id], back_populates="problems", lazy="raise"
    )
    hints: Mapped[list["ProblemHint"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        lazy="raise",
    )
    solutions: Mapped[list["ProblemSolution"]] = relationship(
        back_populates="problem",
        cascade="all, delete-orphan",
        lazy="raise",
    )


class TopicTheory(Base):
    """Редакция объяснения темы: один topic_id, разные edition."""

    __tablename__ = "topic_theories"
    __table_args__ = (
        UniqueConstraint("topic_id", "edition", name="uq_topic_theories_edition"),
        Index("ix_topic_theories_topic", "topic_id", "edition"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    edition: Mapped[int] = mapped_column(Integer, default=1)
    edition_count: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(16), default="text")
    image_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    topic: Mapped[Topic] = relationship(back_populates="theories", lazy="raise")


class ProblemHint(Base):
    __tablename__ = "problem_hints"
    __table_args__ = (
        UniqueConstraint("problem_id", "edition", name="uq_problem_hints_edition"),
        Index("ix_problem_hints_problem", "problem_id", "edition"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE")
    )
    edition: Mapped[int] = mapped_column(Integer, default=1)
    edition_count: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text, default="")

    problem: Mapped[Problem] = relationship(back_populates="hints", lazy="raise")


class ProblemSolution(Base):
    __tablename__ = "problem_solutions"
    __table_args__ = (
        UniqueConstraint("problem_id", "edition", name="uq_problem_solutions_edition"),
        Index("ix_problem_solutions_problem", "problem_id", "edition"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("problems.id", ondelete="CASCADE")
    )
    edition: Mapped[int] = mapped_column(Integer, default=1)
    edition_count: Mapped[int] = mapped_column(Integer, default=1)
    body: Mapped[str] = mapped_column(Text, default="")

    problem: Mapped[Problem] = relationship(back_populates="solutions", lazy="raise")


class LearningSession(Base):
    __tablename__ = "learning_sessions"
    __table_args__ = (Index("ix_sessions_user_active", "user_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    stage: Mapped[str] = mapped_column(String(32), default="theory")
    status: Mapped[str] = mapped_column(String(32), default="active")
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (Index("ix_attempts_session", "session_id", "problem_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[int] = mapped_column(
        ForeignKey("learning_sessions.id", ondelete="CASCADE")
    )
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"))
    submitted: Mapped[str] = mapped_column(String(255), default="")
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    used_help: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now()
    )


class TopicProgress(Base):
    __tablename__ = "topic_progress"
    __table_args__ = (UniqueConstraint("user_id", "topic_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    theory_done: Mapped[bool] = mapped_column(Boolean, default=False)
    training_done: Mapped[bool] = mapped_column(Boolean, default=False)
    assessment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_grade: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    reinforcement_correct: Mapped[int] = mapped_column(Integer, default=0)
    reinforcement_total: Mapped[int] = mapped_column(Integer, default=0)
    mastery: Mapped[str] = mapped_column(String(32), default="not_started")
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, server_default=func.now(), onupdate=func.now()
    )


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        Index("ix_assessment_user_topic", "user_id", "topic_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deadline_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(32), default="in_progress")
    correct_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    grade: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    problem_ids: Mapped[str] = mapped_column(Text, default="")
    panel_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    answers: Mapped[list["AssessmentAnswer"]] = relationship(
        back_populates="attempt",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "problem_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[int] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="CASCADE")
    )
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id"))
    sort_order: Mapped[int] = mapped_column(Integer, default=1)
    submitted: Mapped[str] = mapped_column(String(255), default="")
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    attempt: Mapped[AssessmentAttempt] = relationship(
        back_populates="answers", lazy="raise"
    )


class GradeOption(Base):
    __tablename__ = "grades"

    grade: Mapped[int] = mapped_column(Integer, primary_key=True)


class UserProblemStat(Base):
    __tablename__ = "user_problem_stats"
    __table_args__ = (UniqueConstraint("user_id", "problem_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"))
    last_solved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

