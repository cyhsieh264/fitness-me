from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BodyComposition
from src.utils.time import today


async def log_body_composition(
    db: AsyncSession,
    user_id: int,
    measurement_date: date,
    body_fat_pct: float | None = None,
    weight_kg: float | None = None,
    muscle_mass_kg: float | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    record = BodyComposition(
        user_id=user_id,
        date=measurement_date,
        body_fat_pct=body_fat_pct,
        weight_kg=weight_kg,
        muscle_mass_kg=muscle_mass_kg,
        notes=notes,
    )
    db.add(record)
    await db.flush()

    return {
        "id": record.id,
        "date": measurement_date.isoformat(),
        "body_fat_pct": body_fat_pct,
        "weight_kg": weight_kg,
        "muscle_mass_kg": muscle_mass_kg,
    }


async def get_body_composition_history(
    db: AsyncSession,
    user_id: int,
    days: int = 90,
) -> list[dict[str, object]]:
    cutoff = today() - timedelta(days=days)

    result = await db.execute(
        select(BodyComposition)
        .where(
            BodyComposition.user_id == user_id,
            BodyComposition.date >= cutoff,
        )
        .order_by(BodyComposition.date.desc())
    )
    records = result.scalars().all()

    return [
        {
            "date": r.date.isoformat(),
            "body_fat_pct": r.body_fat_pct,
            "weight_kg": r.weight_kg,
            "muscle_mass_kg": r.muscle_mass_kg,
            "notes": r.notes,
        }
        for r in records
    ]


async def get_body_composition_summary(
    db: AsyncSession,
    user_id: int,
    days: int = 90,
) -> dict[str, object]:
    """Latest measurement, period change, and goal comparison."""
    from src.services.profile import get_profile_summary

    records = await get_body_composition_history(db, user_id, days)
    if not records:
        return {"total_measurements": 0}

    latest = records[0]
    summary: dict[str, object] = {
        "total_measurements": len(records),
        "latest": latest,
    }

    if len(records) > 1:
        earliest = records[-1]
        changes: dict[str, float] = {}
        if latest.get("body_fat_pct") and earliest.get("body_fat_pct"):
            changes["body_fat_pct"] = round(
                latest["body_fat_pct"] - earliest["body_fat_pct"], 1
            )
        if latest.get("weight_kg") and earliest.get("weight_kg"):
            changes["weight_kg"] = round(
                latest["weight_kg"] - earliest["weight_kg"], 1
            )
        if latest.get("muscle_mass_kg") and earliest.get("muscle_mass_kg"):
            changes["muscle_mass_kg"] = round(
                latest["muscle_mass_kg"] - earliest["muscle_mass_kg"], 1
            )
        if changes:
            summary["change"] = changes
            summary["period_start"] = earliest["date"]

    # Goal comparison from user profile
    prof = await get_profile_summary(db, user_id)
    goals: dict[str, object] = {}
    if prof.get("target_body_fat_pct") and latest.get("body_fat_pct"):
        goals["target_body_fat_pct"] = prof["target_body_fat_pct"]
        goals["gap"] = round(
            latest["body_fat_pct"] - prof["target_body_fat_pct"], 1
        )
    if prof.get("target_max_hr"):
        goals["target_max_hr"] = prof["target_max_hr"]
    if goals:
        summary["goals"] = goals

    return summary
