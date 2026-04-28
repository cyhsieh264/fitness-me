"""Tests for delete_records_in_range — the destructive admin operation."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    BodyComposition,
    CardioRecord,
    Exercise,
    MealLog,
    PersonalRecord,
    SessionExercise,
    TrainingSession,
    User,
)
from src.services.admin_ops import delete_records_in_range
from src.services.body_comp import log_body_composition
from src.services.cardio import log_cardio
from src.services.meal_log import log_meal
from src.services.workout import get_or_create_session, record_exercises


async def _seed_strength(db: AsyncSession, user: User, d: date, ex: Exercise) -> None:
    session, _ = await get_or_create_session(db, user.id, d, "self_training")
    await record_exercises(
        db,
        user.id,
        session.id,
        [
            {
                "exercise_name": ex.name_zh,
                "sets": [
                    {
                        "weight_value": 40,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 10,
                        "num_sets": 4,
                    }
                ],
            }
        ],
    )


async def test_delete_clears_full_subtree(
    db: AsyncSession, user: User, today: date, seed_exercises: dict[str, Exercise]
):
    d = today - timedelta(days=2)
    await _seed_strength(db, user, d, seed_exercises["squat"])
    await log_cardio(db, user.id, d, "treadmill", duration_min=30)
    await log_body_composition(db, user.id, d, body_fat_pct=22.5, weight_kg=60)
    await log_meal(db, user.id, d, "lunch", ["燒肉飯"], calories=700)
    await db.flush()

    counts = await delete_records_in_range(db, user.line_user_id, d, d)
    await db.flush()

    assert counts["training_sessions"] == 1
    assert counts["session_exercises"] == 1
    assert counts["exercise_sets"] == 1
    assert counts["cardio_records"] == 1
    assert counts["body_compositions"] == 1
    assert counts["meal_logs"] == 1
    # Single PR was created when seeding strength
    assert counts["personal_records"] >= 0

    # Verify nothing remains for that day
    sessions = (await db.execute(
        select(TrainingSession).where(TrainingSession.date == d)
    )).scalars().all()
    assert sessions == []


async def test_delete_range_only_affects_selected_dates(
    db: AsyncSession, user: User, today: date, seed_exercises: dict[str, Exercise]
):
    keep = today - timedelta(days=10)
    drop_start = today - timedelta(days=4)
    drop_end = today - timedelta(days=2)

    await _seed_strength(db, user, keep, seed_exercises["squat"])
    await _seed_strength(db, user, drop_start, seed_exercises["squat"])
    await _seed_strength(db, user, drop_end, seed_exercises["squat"])
    await db.flush()

    counts = await delete_records_in_range(db, user.line_user_id, drop_start, drop_end)
    await db.flush()

    assert counts["training_sessions"] == 2
    remaining = (
        await db.execute(select(TrainingSession.date).where(TrainingSession.user_id == user.id))
    ).scalars().all()
    assert remaining == [keep]


async def test_delete_unknown_user_returns_zeros(db: AsyncSession, today: date):
    counts = await delete_records_in_range(db, "U_does_not_exist", today, today)
    assert all(v == 0 for v in counts.values())


async def test_delete_empty_range_returns_zeros(
    db: AsyncSession, user: User, today: date
):
    counts = await delete_records_in_range(
        db, user.line_user_id, today - timedelta(days=30), today - timedelta(days=20)
    )
    assert all(v == 0 for v in counts.values())
