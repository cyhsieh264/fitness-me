"""Tests for tool executor dispatch."""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Exercise, User
from src.llm.tool_executor import execute_tool


async def test_log_strength_training(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    args = {
        "session_type": "self_training",
        "date": "2026-03-12",
        "exercises": [
            {
                "exercise_name": "深蹲",
                "sets": [{"weight_value": 40, "reps_min": 10, "num_sets": 4}],
            }
        ],
    }
    result = json.loads(await execute_tool(db, user.id, "log_strength_training", args))

    assert result["session_type"] == "self_training"
    assert result["date"] == "2026-03-12"
    assert len(result["exercises"]) == 1
    assert result["exercises"][0]["exercise_name"] == "槓鈴背蹲"


async def test_log_user_condition_with_exercise(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    args = {
        "category": "cue",
        "description": "Scapula depression",
        "exercise_name": "dip",
    }
    result = json.loads(await execute_tool(db, user.id, "log_user_condition", args))

    assert result["status"] == "recorded"
    assert result["exercise"] == "Dip"


async def test_query_conditions(db: AsyncSession, user: User):
    await execute_tool(
        db,
        user.id,
        "log_user_condition",
        {"category": "posture", "description": "test issue"},
    )
    result = json.loads(await execute_tool(db, user.id, "query_conditions", {}))

    assert len(result["conditions"]) == 1


async def test_query_training_detail(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    await execute_tool(
        db,
        user.id,
        "log_strength_training",
        {
            "session_type": "coach",
            "date": "2026-03-12",
            "exercises": [
                {
                    "exercise_name": "深蹲",
                    "sets": [{"weight_value": 40, "reps_min": 10, "num_sets": 4}],
                },
            ],
        },
    )

    result = json.loads(
        await execute_tool(db, user.id, "query_training_detail", {"date": "2026-03-12"})
    )

    assert len(result["sessions"]) == 1
    assert result["sessions"][0]["exercises"][0]["name"] == "槓鈴背蹲"


async def test_query_exercise_progression(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    for i, w in enumerate([40, 45]):
        await execute_tool(
            db,
            user.id,
            "log_strength_training",
            {
                "session_type": "self_training",
                "date": f"2026-03-{10 + i * 2:02d}",
                "exercises": [
                    {
                        "exercise_name": "深蹲",
                        "sets": [{"weight_value": w, "reps_min": 10, "num_sets": 4}],
                    },
                ],
            },
        )

    result = json.loads(
        await execute_tool(db, user.id, "query_exercise_progression", {"exercise_name": "深蹲"})
    )

    assert result["exercise"] == "槓鈴背蹲"
    assert result["total_sessions"] == 2


async def test_unknown_tool(db: AsyncSession, user: User):
    result = json.loads(await execute_tool(db, user.id, "nonexistent_tool", {}))
    assert "error" in result


async def test_update_user_profile(db: AsyncSession, user: User):
    result = json.loads(
        await execute_tool(
            db,
            user.id,
            "update_user_profile",
            {
                "fitness_goals": "Gain muscle",
                "training_habit": "3x per week",
            },
        )
    )

    assert "fitness_goals" in result
    assert result["fitness_goals"] == "Gain muscle"


async def test_query_exercise_notes(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    await execute_tool(
        db,
        user.id,
        "log_user_condition",
        {
            "category": "cue",
            "description": "Grip inward",
            "exercise_name": "dip",
        },
    )

    result = json.loads(
        await execute_tool(db, user.id, "query_exercise_notes", {"exercise_name": "dip"})
    )

    assert result["exercise"] == "Dip"
    assert len(result["notes"]) == 1
