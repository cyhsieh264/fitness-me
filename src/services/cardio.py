from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import CardioRecord, TrainingSession
from src.services.workout import get_or_create_session
from src.utils.time import window_dates


async def log_cardio(
    db: AsyncSession,
    user_id: int,
    training_date: date,
    cardio_type: str,
    duration_min: int | None = None,
    incline: float | None = None,
    speed_kmh: float | None = None,
    resistance: float | None = None,
    distance_km: float | None = None,
    max_heart_rate: int | None = None,
    avg_heart_rate: int | None = None,
    calories: int | None = None,
    notes: str | None = None,
) -> dict[str, object]:
    session, _ = await get_or_create_session(db, user_id, training_date, "self_training")

    record = CardioRecord(
        session_id=session.id,
        cardio_type=cardio_type,
        duration_min=duration_min,
        incline=incline,
        speed_kmh=speed_kmh,
        resistance=resistance,
        distance_km=distance_km,
        max_heart_rate=max_heart_rate,
        avg_heart_rate=avg_heart_rate,
        calories=calories,
        notes=notes,
    )
    db.add(record)
    await db.flush()

    return {
        "cardio_id": record.id,
        "session_id": session.id,
        "date": training_date.isoformat(),
        "cardio_type": cardio_type,
        "duration_min": duration_min,
        "max_heart_rate": max_heart_rate,
    }


async def get_cardio_history(
    db: AsyncSession,
    user_id: int,
    days: int = 30,
    cardio_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, object]]:
    start, end = window_dates(days, date_from, date_to)

    query = (
        select(CardioRecord, TrainingSession.date)
        .join(TrainingSession)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.date >= start,
        )
        .order_by(TrainingSession.date.desc())
    )
    if end:
        query = query.where(TrainingSession.date <= end)
    if cardio_type:
        query = query.where(CardioRecord.cardio_type == cardio_type)

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "date": session_date.isoformat(),
            "type": r.cardio_type,
            "duration_min": r.duration_min,
            "speed_kmh": r.speed_kmh,
            "incline": r.incline,
            "resistance": r.resistance,
            "distance_km": r.distance_km,
            "max_hr": r.max_heart_rate,
            "avg_hr": r.avg_heart_rate,
            "calories": r.calories,
        }
        for r, session_date in rows
    ]


async def get_cardio_summary(
    db: AsyncSession,
    user_id: int,
    days: int = 30,
    cardio_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, object]:
    """Aggregate stats for LLM trend analysis."""
    records = await get_cardio_history(db, user_id, days, cardio_type, date_from, date_to)
    if not records:
        return {"total_sessions": 0}

    by_type: dict[str, int] = {}
    hr_values: list[int] = []
    durations: list[int] = []

    for r in records:
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1
        if r["max_hr"]:
            hr_values.append(r["max_hr"])
        if r["duration_min"]:
            durations.append(r["duration_min"])

    summary: dict[str, object] = {
        "total_sessions": len(records),
        "by_type": by_type,
    }

    if durations:
        summary["total_duration_min"] = sum(durations)
        summary["avg_duration_min"] = round(sum(durations) / len(durations))

    if hr_values:
        summary["avg_max_hr"] = round(sum(hr_values) / len(hr_values))
        summary["highest_max_hr"] = max(hr_values)
        summary["latest_max_hr"] = hr_values[0]

    return summary
