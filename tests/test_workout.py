"""Tests for workout recording, PR detection, training detail, and exercise progression."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Exercise, User
from src.services.workout import (
    get_exercise_progression,
    get_or_create_session,
    get_personal_records,
    get_training_detail,
    get_training_history,
    record_exercises,
    resolve_exercise,
    save_raw_record,
)


async def test_get_or_create_session(db: AsyncSession, user: User):
    training_date = date(2026, 3, 12)

    session1, is_new1 = await get_or_create_session(db, user.id, training_date, "self_training")
    assert is_new1 is True
    assert session1.date == training_date

    session2, is_new2 = await get_or_create_session(db, user.id, training_date, "coach")
    assert is_new2 is False
    assert session2.id == session1.id


async def test_resolve_exercise_by_alias(db: AsyncSession, seed_exercises: dict[str, Exercise]):
    exercise = await resolve_exercise(db, "深蹲")
    assert exercise is not None
    assert exercise.name_zh == "槓鈴背蹲"


async def test_resolve_exercise_by_name_zh(db: AsyncSession, seed_exercises: dict[str, Exercise]):
    exercise = await resolve_exercise(db, "槓鈴背蹲")
    assert exercise is not None
    assert exercise.name == "Barbell Back Squat"


async def test_resolve_exercise_not_found(db: AsyncSession, seed_exercises: dict[str, Exercise]):
    exercise = await resolve_exercise(db, "不存在的動作")
    assert exercise is None


async def test_record_exercises_with_pr(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    training_date = date(2026, 3, 12)
    session, _ = await get_or_create_session(db, user.id, training_date, "self_training")

    exercises_data = [
        {
            "exercise_name": "深蹲",
            "sets": [
                {
                    "weight_value": 40,
                    "weight_type": "total",
                    "weight_unit": "kg",
                    "reps_min": 10,
                    "num_sets": 4,
                },
            ],
        },
    ]
    results = await record_exercises(db, user.id, session.id, exercises_data)

    assert len(results) == 1
    assert results[0]["exercise_name"] == "槓鈴背蹲"
    assert results[0]["matched"] is True
    assert results[0]["pr"] is not None
    assert results[0]["pr"]["is_first"] is True


async def test_record_unmatched_exercise(db: AsyncSession, user: User, seed_exercises: dict):
    training_date = date(2026, 3, 12)
    session, _ = await get_or_create_session(db, user.id, training_date, "self_training")

    exercises_data = [
        {
            "exercise_name": "自創動作",
            "sets": [{"reps_min": 15, "num_sets": 3}],
        },
    ]
    results = await record_exercises(db, user.id, session.id, exercises_data)

    assert results[0]["exercise_name"] == "自創動作"
    assert results[0]["matched"] is False
    assert results[0]["pr"] is None


async def test_pr_updates_on_heavier_weight(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    d1 = date(2026, 3, 10)
    s1, _ = await get_or_create_session(db, user.id, d1, "self_training")
    await record_exercises(
        db,
        user.id,
        s1.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [
                    {
                        "weight_value": 40,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 10,
                        "num_sets": 4,
                    }
                ],
            },
        ],
    )

    d2 = date(2026, 3, 12)
    s2, _ = await get_or_create_session(db, user.id, d2, "self_training")
    results = await record_exercises(
        db,
        user.id,
        s2.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [
                    {
                        "weight_value": 50,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 8,
                        "num_sets": 3,
                    }
                ],
            },
        ],
    )

    assert results[0]["pr"] is not None
    assert results[0]["pr"]["is_first"] is False
    assert results[0]["pr"]["new_best"] == "50kg"

    prs = await get_personal_records(db, user.id)
    assert len(prs) == 1
    assert prs[0]["best"] == "50kg"


async def test_assisted_pr_lower_is_better(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    d1 = date(2026, 3, 10)
    s1, _ = await get_or_create_session(db, user.id, d1, "self_training")
    await record_exercises(
        db,
        user.id,
        s1.id,
        [
            {
                "exercise_name": "dip",
                "sets": [
                    {
                        "weight_value": 20,
                        "weight_type": "counterweight",
                        "weight_unit": "kg",
                        "reps_min": 8,
                        "num_sets": 3,
                    }
                ],
            },
        ],
    )

    d2 = date(2026, 3, 12)
    s2, _ = await get_or_create_session(db, user.id, d2, "self_training")
    results = await record_exercises(
        db,
        user.id,
        s2.id,
        [
            {
                "exercise_name": "dip",
                "sets": [
                    {
                        "weight_value": 15,
                        "weight_type": "counterweight",
                        "weight_unit": "kg",
                        "reps_min": 8,
                        "num_sets": 3,
                    }
                ],
            },
        ],
    )

    assert results[0]["pr"] is not None
    assert results[0]["pr"]["new_best"] == "15kg counterweight"


async def test_get_training_history(db: AsyncSession, user: User, seed_exercises: dict):
    d = date(2026, 3, 12)
    s, _ = await get_or_create_session(db, user.id, d, "coach")
    await record_exercises(
        db,
        user.id,
        s.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [{"weight_value": 40, "reps_min": 10, "num_sets": 4}],
            },
        ],
    )

    history = await get_training_history(db, user.id, days=7)
    assert len(history) == 1
    assert history[0]["session_type"] == "coach"
    assert "槓鈴背蹲" in history[0]["exercises"]


async def test_get_training_detail(db: AsyncSession, user: User, seed_exercises: dict):
    d = date(2026, 3, 12)
    s, _ = await get_or_create_session(db, user.id, d, "self_training")
    await record_exercises(
        db,
        user.id,
        s.id,
        [
            {
                "exercise_name": "深蹲",
                "sets": [
                    {
                        "weight_value": 40,
                        "weight_type": "total",
                        "weight_unit": "kg",
                        "reps_min": 10,
                        "num_sets": 4,
                    }
                ],
            },
        ],
    )

    detail = await get_training_detail(db, user.id, target_date=d)
    assert len(detail) == 1
    assert detail[0]["exercises"][0]["name"] == "槓鈴背蹲"
    assert len(detail[0]["exercises"][0]["sets"]) == 1
    assert "40" in detail[0]["exercises"][0]["sets"][0]


async def test_get_exercise_progression(db: AsyncSession, user: User, seed_exercises: dict):
    for i, weight in enumerate([40, 42.5, 45]):
        d = date(2026, 3, 1 + i * 3)
        s, _ = await get_or_create_session(db, user.id, d, "self_training")
        await record_exercises(
            db,
            user.id,
            s.id,
            [
                {
                    "exercise_name": "深蹲",
                    "sets": [
                        {
                            "weight_value": weight,
                            "weight_type": "total",
                            "weight_unit": "kg",
                            "reps_min": 10,
                            "num_sets": 4,
                        }
                    ],
                },
            ],
        )

    prog = await get_exercise_progression(db, user.id, "深蹲", days=30)
    assert prog["exercise"] == "槓鈴背蹲"
    assert prog["total_sessions"] == 3
    assert len(prog["progression"]) == 3


async def test_save_raw_record(db: AsyncSession, user: User):
    await save_raw_record(db, user.id, "test content", "workout")
    await db.flush()
