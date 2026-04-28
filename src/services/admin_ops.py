"""Admin maintenance operations.

These are intentionally NOT exposed as LLM tools — they're destructive
batch operations the operator triggers via /admin/* endpoints.
"""

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    BodyComposition,
    BodySegment,
    CardioRecord,
    ExerciseSet,
    MealLog,
    PersonalRecord,
    RawRecord,
    SessionExercise,
    TrainingSession,
    User,
)


async def delete_records_in_range(
    db: AsyncSession,
    line_user_id: str,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """Delete training / cardio / body / meal data for one user in a date range.

    Manual cascade because our FKs aren't ON DELETE CASCADE — we delete
    children before their parents to avoid integrity errors.

    Returns a row-count summary; never raises for "user not found" or
    "nothing in range" — those just return zeros.
    """
    counts = {
        "training_sessions": 0,
        "session_exercises": 0,
        "exercise_sets": 0,
        "cardio_records": 0,
        "raw_records": 0,
        "body_compositions": 0,
        "body_segments": 0,
        "meal_logs": 0,
        "personal_records": 0,
    }

    user = (
        await db.execute(select(User).where(User.line_user_id == line_user_id))
    ).scalar_one_or_none()
    if user is None:
        return counts
    user_id = user.id

    # ---- Training-session subtree ----
    session_ids = (
        await db.execute(
            select(TrainingSession.id).where(
                TrainingSession.user_id == user_id,
                TrainingSession.date.between(start_date, end_date),
            )
        )
    ).scalars().all()

    if session_ids:
        se_ids = (
            await db.execute(
                select(SessionExercise.id).where(
                    SessionExercise.session_id.in_(session_ids)
                )
            )
        ).scalars().all()
        if se_ids:
            r = await db.execute(
                delete(ExerciseSet).where(ExerciseSet.session_exercise_id.in_(se_ids))
            )
            counts["exercise_sets"] = r.rowcount or 0
        r = await db.execute(
            delete(SessionExercise).where(SessionExercise.session_id.in_(session_ids))
        )
        counts["session_exercises"] = r.rowcount or 0
        r = await db.execute(
            delete(CardioRecord).where(CardioRecord.session_id.in_(session_ids))
        )
        counts["cardio_records"] = r.rowcount or 0
        r = await db.execute(
            delete(RawRecord).where(RawRecord.session_id.in_(session_ids))
        )
        counts["raw_records"] = r.rowcount or 0
        r = await db.execute(
            delete(TrainingSession).where(TrainingSession.id.in_(session_ids))
        )
        counts["training_sessions"] = r.rowcount or 0

    # ---- Body composition subtree ----
    bc_ids = (
        await db.execute(
            select(BodyComposition.id).where(
                BodyComposition.user_id == user_id,
                BodyComposition.date.between(start_date, end_date),
            )
        )
    ).scalars().all()
    if bc_ids:
        r = await db.execute(
            delete(BodySegment).where(BodySegment.body_composition_id.in_(bc_ids))
        )
        counts["body_segments"] = r.rowcount or 0
        r = await db.execute(
            delete(BodyComposition).where(BodyComposition.id.in_(bc_ids))
        )
        counts["body_compositions"] = r.rowcount or 0

    # ---- Meal logs (flat) ----
    r = await db.execute(
        delete(MealLog).where(
            MealLog.user_id == user_id,
            MealLog.date.between(start_date, end_date),
        )
    )
    counts["meal_logs"] = r.rowcount or 0

    # ---- Personal records achieved in the range ----
    # Aggregate maxes; the achieving session is gone so the PR row is stale.
    r = await db.execute(
        delete(PersonalRecord).where(
            PersonalRecord.user_id == user_id,
            PersonalRecord.achieved_date.between(start_date, end_date),
        )
    )
    counts["personal_records"] = r.rowcount or 0

    return counts
