from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import BodyComposition, CardioRecord, TrainingSession
from src.services.workout import get_or_create_session
from src.utils.time import window_dates

# MET (Metabolic Equivalent) values per activity. When speed/intensity hints
# are available we pick a higher band; otherwise the moderate row.
# Source: 2011 Compendium of Physical Activities (commonly cited values).
_MET_TABLE: dict[str, float] = {
    "treadmill_walk": 3.8,    # speed < 6 km/h
    "treadmill_jog": 7.0,     # 6 ≤ speed < 9
    "treadmill_run": 11.0,    # speed ≥ 9
    "spinning": 8.5,
    "rowing": 7.0,
    "cycling_easy": 5.0,      # speed < 16
    "cycling_moderate": 7.5,  # 16-20
    "cycling_vigorous": 10.0, # > 20
    "running_moderate": 9.8,
    "running_fast": 12.5,     # speed ≥ 12
    "swimming": 6.0,
    "elliptical": 5.0,
    "hiking": 6.0,
    "other": 6.0,
}

# Fallback weight when the user has no body_compositions row yet.
_DEFAULT_WEIGHT_KG = 65.0


def _met_for(cardio_type: str, speed_kmh: float | None) -> float:
    """Pick the right MET row for an activity + intensity hint."""
    if cardio_type == "treadmill":
        if speed_kmh is None:
            return _MET_TABLE["treadmill_jog"]
        if speed_kmh < 6:
            return _MET_TABLE["treadmill_walk"]
        if speed_kmh < 9:
            return _MET_TABLE["treadmill_jog"]
        return _MET_TABLE["treadmill_run"]
    if cardio_type == "cycling":
        if speed_kmh is None or speed_kmh < 16:
            return _MET_TABLE["cycling_easy"]
        if speed_kmh < 20:
            return _MET_TABLE["cycling_moderate"]
        return _MET_TABLE["cycling_vigorous"]
    if cardio_type == "running":
        if speed_kmh is not None and speed_kmh >= 12:
            return _MET_TABLE["running_fast"]
        return _MET_TABLE["running_moderate"]
    return _MET_TABLE.get(cardio_type, _MET_TABLE["other"])


async def _latest_weight_kg(db: AsyncSession, user_id: int) -> float:
    """Return the most recent recorded weight, or the default if none exists."""
    result = await db.execute(
        select(BodyComposition.weight_kg)
        .where(BodyComposition.user_id == user_id, BodyComposition.weight_kg.isnot(None))
        .order_by(BodyComposition.date.desc())
        .limit(1)
    )
    weight = result.scalar_one_or_none()
    return float(weight) if weight else _DEFAULT_WEIGHT_KG


def _estimate_calories(
    cardio_type: str,
    duration_min: int | None,
    speed_kmh: float | None,
    weight_kg: float,
) -> int | None:
    if duration_min is None or duration_min <= 0 or weight_kg <= 0:
        return None
    met = _met_for(cardio_type, speed_kmh)
    return round(met * weight_kg * 3.5 * duration_min / 200)


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

    # Auto-estimate calories from MET × weight × duration when the caller
    # didn't supply one. User-provided values (e.g. from a HR monitor) win.
    estimated = False
    if calories is None:
        weight_kg = await _latest_weight_kg(db, user_id)
        calories = _estimate_calories(cardio_type, duration_min, speed_kmh, weight_kg)
        estimated = calories is not None

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
        "distance_km": distance_km,
        "max_heart_rate": max_heart_rate,
        "calories": calories,
        "calories_estimated": estimated,
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
