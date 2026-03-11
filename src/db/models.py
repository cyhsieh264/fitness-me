from datetime import date

from sqlalchemy import (
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    profile: Mapped["UserProfile | None"] = relationship(back_populates="user", uselist=False)
    conditions: Mapped[list["UserCondition"]] = relationship(back_populates="user")
    raw_records: Mapped[list["RawRecord"]] = relationship(back_populates="user")
    training_sessions: Mapped[list["TrainingSession"]] = relationship(back_populates="user")
    personal_records: Mapped[list["PersonalRecord"]] = relationship(back_populates="user")
    body_compositions: Mapped[list["BodyComposition"]] = relationship(back_populates="user")
    daily_interactions: Mapped[list["DailyInteraction"]] = relationship(back_populates="user")
    chat_messages: Mapped[list["ChatMessage"]] = relationship(back_populates="user")


class UserProfile(Base):
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    fitness_goals: Mapped[str | None] = mapped_column(Text)
    training_habit: Mapped[str | None] = mapped_column(Text)
    cardio_status: Mapped[str | None] = mapped_column(Text)
    target_body_fat_pct: Mapped[float | None] = mapped_column(Float)
    target_max_hr: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="profile")


class UserCondition(Base):
    __tablename__ = "user_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action_item: Mapped[str | None] = mapped_column(Text)
    exercise_id: Mapped[int | None] = mapped_column(ForeignKey("exercises.id"))
    source_session_id: Mapped[int | None] = mapped_column(ForeignKey("training_sessions.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_at: Mapped[int | None] = mapped_column(Integer)

    user: Mapped["User"] = relationship(back_populates="conditions")
    exercise: Mapped["Exercise | None"] = relationship()
    source_session: Mapped["TrainingSession | None"] = relationship()


class RawRecord(Base):
    __tablename__ = "raw_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    record_type: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("training_sessions.id"))
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="raw_records")
    session: Mapped["TrainingSession | None"] = relationship()


class MuscleGroup(Base):
    __tablename__ = "muscle_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_zh: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    name_zh: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    equipment: Mapped[str] = mapped_column(String, nullable=False)
    movement_pattern: Mapped[str] = mapped_column(String, nullable=False)
    is_assisted: Mapped[bool] = mapped_column(Boolean, default=False)

    aliases: Mapped[list["ExerciseAlias"]] = relationship(back_populates="exercise")
    muscles: Mapped[list["ExerciseMuscle"]] = relationship(back_populates="exercise")


class ExerciseAlias(Base):
    __tablename__ = "exercise_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    alias: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    exercise: Mapped["Exercise"] = relationship(back_populates="aliases")


class ExerciseMuscle(Base):
    __tablename__ = "exercise_muscles"

    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), primary_key=True)
    muscle_group_id: Mapped[int] = mapped_column(ForeignKey("muscle_groups.id"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True)

    exercise: Mapped["Exercise"] = relationship(back_populates="muscles")
    muscle_group: Mapped["MuscleGroup"] = relationship()


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    __table_args__ = (Index("ix_training_sessions_user_date", "user_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    session_type: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="training_sessions")
    exercises: Mapped[list["SessionExercise"]] = relationship(
        back_populates="session", order_by="SessionExercise.order_num"
    )
    cardio_records: Mapped[list["CardioRecord"]] = relationship(back_populates="session")


class SessionExercise(Base):
    __tablename__ = "session_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), nullable=False)
    exercise_id: Mapped[int | None] = mapped_column(ForeignKey("exercises.id"))
    exercise_name: Mapped[str] = mapped_column(String, nullable=False)
    order_num: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String, default="working")
    notes: Mapped[str | None] = mapped_column(Text)

    session: Mapped["TrainingSession"] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise | None"] = relationship()
    sets: Mapped[list["ExerciseSet"]] = relationship(back_populates="session_exercise")


class ExerciseSet(Base):
    __tablename__ = "exercise_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_exercise_id: Mapped[int] = mapped_column(
        ForeignKey("session_exercises.id"), nullable=False
    )
    weight_value: Mapped[float | None] = mapped_column(Float)
    weight_type: Mapped[str | None] = mapped_column(String)
    weight_unit: Mapped[str] = mapped_column(String, default="kg")
    band_info: Mapped[str | None] = mapped_column(String)
    reps_min: Mapped[int | None] = mapped_column(Integer)
    reps_max: Mapped[int | None] = mapped_column(Integer)
    num_sets: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    is_each_side: Mapped[bool] = mapped_column(Boolean, default=False)

    session_exercise: Mapped["SessionExercise"] = relationship(back_populates="sets")


class PersonalRecord(Base):
    __tablename__ = "personal_records"
    __table_args__ = (UniqueConstraint("user_id", "exercise_id", name="uq_pr_user_exercise"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    best_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    weight_display: Mapped[str | None] = mapped_column(String)
    achieved_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_target_kg: Mapped[float | None] = mapped_column(Float)

    user: Mapped["User"] = relationship(back_populates="personal_records")
    exercise: Mapped["Exercise"] = relationship()


class CardioRecord(Base):
    __tablename__ = "cardio_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), nullable=False)
    cardio_type: Mapped[str] = mapped_column(String, nullable=False)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    incline: Mapped[float | None] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    resistance: Mapped[float | None] = mapped_column(Float)
    distance_km: Mapped[float | None] = mapped_column(Float)
    max_heart_rate: Mapped[int | None] = mapped_column(Integer)
    avg_heart_rate: Mapped[int | None] = mapped_column(Integer)
    calories: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    session: Mapped["TrainingSession"] = relationship(back_populates="cardio_records")


class BodyComposition(Base):
    __tablename__ = "body_compositions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    body_fat_pct: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    muscle_mass_kg: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="body_compositions")


class DailyInteraction(Base):
    __tablename__ = "daily_interactions"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_daily_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    push_sent_at: Mapped[int | None] = mapped_column(Integer)
    user_plan: Mapped[str | None] = mapped_column(String)
    user_response: Mapped[str | None] = mapped_column(Text)
    bot_suggestion: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[int | None] = mapped_column(Integer)

    user: Mapped["User"] = relationship(back_populates="daily_interactions")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="chat_messages")
