"""Shared test fixtures with in-memory SQLite."""

import os

os.environ.setdefault("LINE_CHANNEL_SECRET", "test_secret")
os.environ.setdefault("LINE_CHANNEL_ACCESS_TOKEN", "test_token")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, Exercise, ExerciseAlias, MuscleGroup, User
from src.utils.time import timestamp


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            yield session


@pytest.fixture
async def user(db: AsyncSession) -> User:
    u = User(line_user_id="U_TEST_001", display_name="Test User", created_at=timestamp())
    db.add(u)
    await db.flush()
    return u


@pytest.fixture
async def seed_exercises(db: AsyncSession) -> dict[str, Exercise]:
    """Seed a few exercises for testing."""
    mg_quads = MuscleGroup(name="Quadriceps", name_zh="股四頭肌", category="lower_body")
    mg_glutes = MuscleGroup(name="Glutes", name_zh="臀大肌", category="lower_body")
    mg_chest = MuscleGroup(name="Chest", name_zh="胸肌", category="upper_push")
    mg_triceps = MuscleGroup(name="Triceps", name_zh="三頭肌", category="upper_push")
    db.add_all([mg_quads, mg_glutes, mg_chest, mg_triceps])
    await db.flush()

    squat = Exercise(
        name="Barbell Back Squat",
        name_zh="槓鈴背蹲",
        type="strength",
        equipment="barbell",
        movement_pattern="squat",
        is_assisted=False,
    )
    dip = Exercise(
        name="Dip (Assisted)",
        name_zh="Dip",
        type="strength",
        equipment="machine",
        movement_pattern="horizontal_push",
        is_assisted=True,
    )
    db.add_all([squat, dip])
    await db.flush()

    db.add_all(
        [
            ExerciseAlias(exercise_id=squat.id, alias="深蹲"),
            ExerciseAlias(exercise_id=squat.id, alias="槓鈴深蹲"),
            ExerciseAlias(exercise_id=dip.id, alias="dip"),
        ]
    )
    await db.flush()

    return {"squat": squat, "dip": dip}


@pytest.fixture
def today() -> date:
    return date.today()
