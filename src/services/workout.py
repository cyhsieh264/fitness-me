from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Exercise,
    ExerciseAlias,
    ExerciseSet,
    PersonalRecord,
    RawRecord,
    SessionExercise,
    TrainingSession,
)
from src.utils.time import timestamp, today

LB_TO_KG = 0.453592


async def get_or_create_session(
    db: AsyncSession,
    user_id: int,
    training_date: date,
    session_type: str,
) -> tuple[TrainingSession, bool]:
    """Return (session, is_new). Reuses existing session for same user+date."""
    result = await db.execute(
        select(TrainingSession).where(
            TrainingSession.user_id == user_id,
            TrainingSession.date == training_date,
        )
    )
    session = result.scalar_one_or_none()
    if session:
        return session, False

    session = TrainingSession(
        user_id=user_id,
        date=training_date,
        session_type=session_type,
        recorded_at=timestamp(),
    )
    db.add(session)
    await db.flush()
    return session, True


async def resolve_exercise(db: AsyncSession, name: str) -> Exercise | None:
    """Look up exercise by alias, then by name_zh / name."""
    result = await db.execute(
        select(Exercise).join(ExerciseAlias).where(ExerciseAlias.alias == name)
    )
    exercise: Exercise | None = result.scalar_one_or_none()
    if exercise:
        return exercise

    result = await db.execute(
        select(Exercise).where((Exercise.name_zh == name) | (Exercise.name == name))
    )
    found: Exercise | None = result.scalar_one_or_none()
    return found


async def _next_order_num(db: AsyncSession, session_id: int) -> int:
    result = await db.execute(
        select(SessionExercise.order_num)
        .where(SessionExercise.session_id == session_id)
        .order_by(SessionExercise.order_num.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return (last or 0) + 1


async def record_exercises(
    db: AsyncSession,
    user_id: int,
    session_id: int,
    exercises_data: list[dict],
) -> list[dict]:
    """Record exercises + sets. Returns list with resolved names and PR info."""
    results = []
    order_num = await _next_order_num(db, session_id)

    for ex_data in exercises_data:
        exercise = await resolve_exercise(db, ex_data["exercise_name"])
        display_name = exercise.name_zh if exercise else ex_data["exercise_name"]

        session_exercise = SessionExercise(
            session_id=session_id,
            exercise_id=exercise.id if exercise else None,
            exercise_name=display_name,
            order_num=order_num,
            raw_text=ex_data.get("raw_text"),
            category=ex_data.get("category", "working"),
            notes=ex_data.get("notes"),
        )
        db.add(session_exercise)
        await db.flush()

        best_pr = None
        for set_data in ex_data.get("sets", []):
            exercise_set = ExerciseSet(
                session_exercise_id=session_exercise.id,
                weight_value=set_data.get("weight_value"),
                weight_type=set_data.get("weight_type", "total"),
                weight_unit=set_data.get("weight_unit", "kg"),
                band_info=set_data.get("band_info"),
                reps_min=set_data.get("reps_min"),
                reps_max=set_data.get("reps_max"),
                num_sets=set_data.get("num_sets"),
                duration_sec=set_data.get("duration_sec"),
                is_each_side=set_data.get("is_each_side", False),
            )
            db.add(exercise_set)

            if exercise and set_data.get("weight_value") is not None:
                pr = await _check_pr(
                    db,
                    user_id,
                    exercise,
                    set_data["weight_value"],
                    set_data.get("weight_type", "total"),
                    set_data.get("weight_unit", "kg"),
                )
                if pr and (best_pr is None or pr["total_kg"] > best_pr["total_kg"]):
                    best_pr = pr

        results.append(
            {
                "exercise_name": display_name,
                "matched": exercise is not None,
                "pr": best_pr,
            }
        )
        order_num += 1

    return results


def _normalize_weight_kg(
    weight_value: float,
    weight_type: str,
    weight_unit: str,
) -> float | None:
    """Normalize to total kg for PR comparison. Returns None if not comparable."""
    if weight_type in ("band", "bodyweight"):
        return None

    total = weight_value
    if weight_type == "per_side":
        total = weight_value * 2
    if weight_unit == "lb":
        total *= LB_TO_KG
    return total


async def _check_pr(
    db: AsyncSession,
    user_id: int,
    exercise: Exercise,
    weight_value: float,
    weight_type: str,
    weight_unit: str,
) -> dict | None:
    total_kg = _normalize_weight_kg(weight_value, weight_type, weight_unit)
    if total_kg is None:
        return None

    result = await db.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user_id,
            PersonalRecord.exercise_id == exercise.id,
        )
    )
    current_pr = result.scalar_one_or_none()

    is_new = False
    if current_pr is None:
        is_new = True
    elif exercise.is_assisted:
        is_new = total_kg < current_pr.best_weight_kg
    else:
        is_new = total_kg > current_pr.best_weight_kg

    if not is_new:
        return None

    display = _build_display(weight_value, weight_type, weight_unit)
    old_display = current_pr.weight_display if current_pr else None
    is_first = current_pr is None

    increment = 2.5 if total_kg > 20 else 1.25
    next_target = total_kg - increment if exercise.is_assisted else total_kg + increment

    if current_pr:
        current_pr.best_weight_kg = total_kg
        current_pr.weight_display = display
        current_pr.achieved_date = today()
        current_pr.next_target_kg = next_target
    else:
        db.add(
            PersonalRecord(
                user_id=user_id,
                exercise_id=exercise.id,
                best_weight_kg=total_kg,
                weight_display=display,
                achieved_date=today(),
                next_target_kg=next_target,
            )
        )

    return {
        "exercise_name": exercise.name_zh,
        "new_best": display,
        "old_best": old_display,
        "is_first": is_first,
        "total_kg": total_kg,
    }


def _build_display(weight_value: float, weight_type: str, weight_unit: str) -> str:
    unit = weight_unit
    if weight_type == "per_side":
        return f"{weight_value}{unit} each"
    if weight_type == "counterweight":
        return f"{weight_value}{unit} counterweight"
    return f"{weight_value}{unit}"


async def save_raw_record(
    db: AsyncSession,
    user_id: int,
    content: str,
    record_type: str,
    source: str = "line_message",
    session_id: int | None = None,
) -> None:
    db.add(
        RawRecord(
            user_id=user_id,
            source=source,
            content=content,
            record_type=record_type,
            session_id=session_id,
            created_at=timestamp(),
        )
    )


async def get_training_history(
    db: AsyncSession,
    user_id: int,
    days: int = 7,
) -> list[dict]:
    cutoff = today() - timedelta(days=days)

    result = await db.execute(
        select(TrainingSession)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.date >= cutoff,
        )
        .order_by(TrainingSession.date.desc())
    )
    sessions = result.scalars().all()

    history = []
    for s in sessions:
        ex_result = await db.execute(
            select(SessionExercise.exercise_name)
            .where(SessionExercise.session_id == s.id)
            .order_by(SessionExercise.order_num)
        )
        ex_names = list(ex_result.scalars().all())

        history.append(
            {
                "date": s.date.isoformat(),
                "session_type": s.session_type,
                "exercises": ex_names,
            }
        )

    return history


def _format_set_compact(s: ExerciseSet) -> str:
    """Format a set in compact notation like '40kg*10*4' for LLM readability."""
    parts: list[str] = []

    if s.weight_type == "bodyweight":
        parts.append("bw")
    elif s.weight_type == "band":
        parts.append(f"band({s.band_info or '?'})")
    elif s.weight_value is not None:
        w = f"{s.weight_value}{s.weight_unit}"
        if s.weight_type == "per_side":
            w += " each"
        elif s.weight_type == "counterweight":
            w += " cw"
        parts.append(w)

    if s.duration_sec is not None:
        parts.append(f"{s.duration_sec}s")
    elif s.reps_min is not None:
        if s.reps_max and s.reps_max != s.reps_min:
            parts.append(f"{s.reps_min}-{s.reps_max}")
        else:
            parts.append(str(s.reps_min))

    if s.num_sets and s.num_sets > 1:
        parts.append(str(s.num_sets))

    result = "*".join(parts)
    if s.is_each_side:
        result += " each side"
    return result


async def get_training_detail(
    db: AsyncSession,
    user_id: int,
    days: int = 7,
    target_date: date | None = None,
) -> list[dict]:
    """Get full training detail with sets/weights/reps."""
    if target_date:
        date_filter = TrainingSession.date == target_date
    else:
        cutoff = today() - timedelta(days=days)
        date_filter = TrainingSession.date >= cutoff

    result = await db.execute(
        select(TrainingSession)
        .where(TrainingSession.user_id == user_id, date_filter)
        .order_by(TrainingSession.date.desc())
    )
    sessions = result.scalars().all()

    detail = []
    for s in sessions:
        ex_result = await db.execute(
            select(SessionExercise)
            .where(SessionExercise.session_id == s.id)
            .order_by(SessionExercise.order_num)
        )
        exercises = []
        for se in ex_result.scalars().all():
            sets_result = await db.execute(
                select(ExerciseSet).where(ExerciseSet.session_exercise_id == se.id)
            )
            sets_display = [_format_set_compact(es) for es in sets_result.scalars().all()]

            ex_dict: dict = {
                "name": se.exercise_name,
                "sets": sets_display,
            }
            if se.category != "working":
                ex_dict["category"] = se.category
            if se.notes:
                ex_dict["notes"] = se.notes
            exercises.append(ex_dict)

        session_dict: dict = {
            "date": s.date.isoformat(),
            "session_type": s.session_type,
            "exercises": exercises,
        }
        if s.notes:
            session_dict["notes"] = s.notes
        detail.append(session_dict)

    return detail


async def get_exercise_progression(
    db: AsyncSession,
    user_id: int,
    exercise_name: str,
    days: int = 90,
) -> dict:
    """Get weight progression for a specific exercise over time."""
    exercise = await resolve_exercise(db, exercise_name)
    display_name = exercise.name_zh if exercise else exercise_name

    cutoff = today() - timedelta(days=days)

    query = (
        select(SessionExercise)
        .join(TrainingSession)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.date >= cutoff,
        )
        .order_by(TrainingSession.date.asc())
    )

    if exercise:
        query = query.where(SessionExercise.exercise_id == exercise.id)
    else:
        query = query.where(SessionExercise.exercise_name == exercise_name)

    result = await db.execute(query)
    session_exercises = result.scalars().all()

    progression = []
    for se in session_exercises:
        session: TrainingSession | None = await db.get(TrainingSession, se.session_id)
        if not session:
            continue

        sets_result = await db.execute(
            select(ExerciseSet).where(ExerciseSet.session_exercise_id == se.id)
        )
        sets_display = [_format_set_compact(es) for es in sets_result.scalars().all()]

        progression.append(
            {
                "date": session.date.isoformat(),
                "sets": sets_display,
            }
        )

    return {
        "exercise": display_name,
        "period_days": days,
        "total_sessions": len(progression),
        "progression": progression,
    }


async def get_personal_records(
    db: AsyncSession,
    user_id: int,
    exercise_name: str | None = None,
) -> list[dict]:
    query = (
        select(PersonalRecord)
        .where(PersonalRecord.user_id == user_id)
        .order_by(PersonalRecord.achieved_date.desc())
    )
    result = await db.execute(query)
    records = result.scalars().all()

    prs = []
    for pr in records:
        exercise = await db.get(Exercise, pr.exercise_id)
        if not exercise:
            continue
        if exercise_name and exercise_name.lower() not in (
            exercise.name.lower(),
            exercise.name_zh,
        ):
            continue
        prs.append(
            {
                "exercise": exercise.name_zh,
                "best": pr.weight_display or f"{pr.best_weight_kg}kg",
                "date": pr.achieved_date.isoformat(),
                "next_target_kg": pr.next_target_kg,
            }
        )

    return prs
