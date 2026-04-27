import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import BodyComposition, BodySegment
from src.utils.time import window_dates


async def log_body_composition(
    db: AsyncSession,
    user_id: int,
    measurement_date: date,
    body_fat_pct: float | None = None,
    weight_kg: float | None = None,
    muscle_mass_kg: float | None = None,
    visceral_fat_level: int | None = None,
    bmr: int | None = None,
    score: int | None = None,
    inbody_data: dict | None = None,
    segments: list[dict] | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    record = BodyComposition(
        user_id=user_id,
        date=measurement_date,
        body_fat_pct=body_fat_pct,
        weight_kg=weight_kg,
        muscle_mass_kg=muscle_mass_kg,
        visceral_fat_level=visceral_fat_level,
        bmr=bmr,
        score=score,
        inbody_data=json.dumps(inbody_data, ensure_ascii=False) if inbody_data else None,
        notes=notes,
    )
    db.add(record)
    await db.flush()

    if segments:
        for seg in segments:
            db.add(BodySegment(
                body_composition_id=record.id,
                segment=seg["segment"],
                muscle_mass_kg=seg.get("muscle_mass_kg"),
                muscle_grade=seg.get("muscle_grade"),
                fat_mass_kg=seg.get("fat_mass_kg"),
                fat_grade=seg.get("fat_grade"),
            ))
        await db.flush()

    result: dict[str, object] = {
        "id": record.id,
        "date": measurement_date.isoformat(),
        "body_fat_pct": body_fat_pct,
        "weight_kg": weight_kg,
        "muscle_mass_kg": muscle_mass_kg,
    }
    if visceral_fat_level is not None:
        result["visceral_fat_level"] = visceral_fat_level
    if bmr is not None:
        result["bmr"] = bmr
    if score is not None:
        result["score"] = score
    if segments:
        result["segments"] = segments
    return result


async def get_body_composition_history(
    db: AsyncSession,
    user_id: int,
    days: int = 90,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, object]]:
    start, end = window_dates(days, date_from, date_to)

    query = (
        select(BodyComposition)
        .options(selectinload(BodyComposition.segments))
        .where(
            BodyComposition.user_id == user_id,
            BodyComposition.date >= start,
        )
        .order_by(BodyComposition.date.desc())
    )
    if end:
        query = query.where(BodyComposition.date <= end)

    result = await db.execute(query)
    records = result.scalars().all()

    return [_record_to_dict(r) for r in records]


def _record_to_dict(r: BodyComposition) -> dict[str, object]:
    d: dict[str, object] = {
        "date": r.date.isoformat(),
        "body_fat_pct": r.body_fat_pct,
        "weight_kg": r.weight_kg,
        "muscle_mass_kg": r.muscle_mass_kg,
    }
    if r.visceral_fat_level is not None:
        d["visceral_fat_level"] = r.visceral_fat_level
    if r.bmr is not None:
        d["bmr"] = r.bmr
    if r.score is not None:
        d["score"] = r.score
    if r.segments:
        d["segments"] = [
            {
                "segment": s.segment,
                "muscle_mass_kg": s.muscle_mass_kg,
                "muscle_grade": s.muscle_grade,
                "fat_mass_kg": s.fat_mass_kg,
                "fat_grade": s.fat_grade,
            }
            for s in r.segments
        ]
    if r.notes:
        d["notes"] = r.notes
    return d


async def get_body_composition_summary(
    db: AsyncSession,
    user_id: int,
    days: int = 90,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, object]:
    """Latest measurement, period change, and goal comparison."""
    from src.services.profile import get_profile_summary

    records = await get_body_composition_history(db, user_id, days, date_from, date_to)
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
