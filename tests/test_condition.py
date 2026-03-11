"""Tests for condition tracking and exercise-linked notes."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Exercise, User
from src.services.condition import (
    add_condition,
    get_active_conditions,
    get_exercise_notes,
    resolve_condition,
)


async def test_add_and_get_conditions(db: AsyncSession, user: User):
    await add_condition(db, user.id, "posture", "Left pelvis higher")
    await add_condition(db, user.id, "injury", "Right shoulder discomfort")
    await db.flush()

    conditions = await get_active_conditions(db, user.id)
    assert len(conditions) == 2
    categories = {c["category"] for c in conditions}
    assert categories == {"posture", "injury"}


async def test_resolve_condition(db: AsyncSession, user: User):
    cond = await add_condition(db, user.id, "weakness", "Weak right glute")
    await db.flush()

    ok = await resolve_condition(db, user.id, cond.id)
    assert ok is True

    conditions = await get_active_conditions(db, user.id)
    assert len(conditions) == 0


async def test_resolve_nonexistent_condition(db: AsyncSession, user: User):
    ok = await resolve_condition(db, user.id, 9999)
    assert ok is False


async def test_exercise_linked_condition(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    dip = seed_exercises["dip"]
    await add_condition(db, user.id, "cue", "Scapula depression", exercise_id=dip.id)
    await add_condition(db, user.id, "cue", "Grip inward rotation", exercise_id=dip.id)
    await db.flush()

    conditions = await get_active_conditions(db, user.id)
    assert len(conditions) == 2
    assert conditions[0].get("exercise") == "Dip"

    notes = await get_exercise_notes(db, user.id, dip.id)
    assert len(notes) == 2


async def test_exercise_notes_only_returns_linked(
    db: AsyncSession, user: User, seed_exercises: dict[str, Exercise]
):
    dip = seed_exercises["dip"]
    squat = seed_exercises["squat"]

    await add_condition(db, user.id, "cue", "Dip note", exercise_id=dip.id)
    await add_condition(db, user.id, "cue", "Squat note", exercise_id=squat.id)
    await add_condition(db, user.id, "posture", "General posture issue")
    await db.flush()

    dip_notes = await get_exercise_notes(db, user.id, dip.id)
    assert len(dip_notes) == 1
    assert dip_notes[0]["description"] == "Dip note"

    squat_notes = await get_exercise_notes(db, user.id, squat.id)
    assert len(squat_notes) == 1
