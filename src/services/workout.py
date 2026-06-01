from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Exercise,
    ExerciseAlias,
    ExerciseMuscle,
    ExerciseSet,
    MuscleGroup,
    MuscleGroupAlias,
    PersonalRecord,
    RawRecord,
    SessionExercise,
    TrainingSession,
)
from src.utils.time import timestamp, today, window_dates

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


async def search_exercises(
    db: AsyncSession,
    *,
    query: str | None = None,
    muscle_group: str | None = None,
    movement_pattern: str | None = None,
) -> list[Exercise]:
    """Fuzzy / muscle / movement-pattern lookup for exercises.

    - query: case-insensitive substring against Exercise.name, Exercise.name_zh,
      or any ExerciseAlias.alias. Plain folks' words like "深蹲" / "硬舉" /
      "划船" will land here.
    - muscle_group: matches by (a) substring on MuscleGroup.name /
      MuscleGroup.name_zh OR (b) exact case-insensitive hit on
      MuscleGroupAlias.alias. Joins via ExerciseMuscle (primary or secondary).
      Substring covers "三頭" / "臀" / "tricep" / "股四頭"; the alias table
      covers colloquial words whose Chinese root doesn't appear in the formal
      muscle name: "肩" / "背" / "腿" / "核心".
    - movement_pattern: exact match (case-insensitive) on
      Exercise.movement_pattern.

    Multiple filters AND together. Returns [] when no filter is provided —
    "list every exercise" is never useful as a default and would dump the
    entire catalogue into the LLM.
    """
    if not (query or muscle_group or movement_pattern):
        return []

    stmt = select(Exercise)

    if query:
        needle = f"%{query.lower()}%"
        alias_match = select(ExerciseAlias.exercise_id).where(
            func.lower(ExerciseAlias.alias).like(needle)
        )
        stmt = stmt.where(
            or_(
                func.lower(Exercise.name).like(needle),
                func.lower(Exercise.name_zh).like(needle),
                Exercise.id.in_(alias_match),
            )
        )

    if muscle_group:
        # Match strategy (any of):
        #   - substring on MuscleGroup.name (English, case-insensitive)
        #   - substring on MuscleGroup.name_zh (so "三頭" -> 三頭肌)
        #   - exact (case-insensitive) hit on a curated MuscleGroupAlias row,
        #     used for words that don't share a root with the formal name:
        #     「肩」 -> 三角肌 x3, 「背」 -> 闊背肌 + 菱形肌 + 斜方肌,
        #     「核心」 -> 腹直/腹斜/腹橫 / etc.
        mg_lower = muscle_group.lower()
        mg_needle = f"%{mg_lower}%"
        alias_hit = select(MuscleGroupAlias.muscle_group_id).where(
            func.lower(MuscleGroupAlias.alias) == mg_lower
        )
        muscle_match = (
            select(ExerciseMuscle.exercise_id)
            .join(MuscleGroup, ExerciseMuscle.muscle_group_id == MuscleGroup.id)
            .where(
                or_(
                    func.lower(MuscleGroup.name).like(mg_needle),
                    func.lower(MuscleGroup.name_zh).like(mg_needle),
                    MuscleGroup.id.in_(alias_hit),
                )
            )
        )
        stmt = stmt.where(Exercise.id.in_(muscle_match))

    if movement_pattern:
        stmt = stmt.where(func.lower(Exercise.movement_pattern) == movement_pattern.lower())

    stmt = stmt.order_by(Exercise.id)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    # Dedup (shouldn't repeat with the joinless form above, but keeps
    # this safe if a future branch adds an outer join).
    seen: set[int] = set()
    out: list[Exercise] = []
    for ex in rows:
        if ex.id in seen:
            continue
        seen.add(ex.id)
        out.append(ex)
    return out


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
    training_date: date | None = None,
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
                    training_date=training_date,
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
    training_date: date | None = None,
) -> dict | None:
    achieved_on = training_date or today()
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
        current_pr.achieved_date = achieved_on
        current_pr.next_target_kg = next_target
    else:
        db.add(
            PersonalRecord(
                user_id=user_id,
                exercise_id=exercise.id,
                best_weight_kg=total_kg,
                weight_display=display,
                achieved_date=achieved_on,
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
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    start, end = window_dates(days, date_from, date_to)

    query = (
        select(TrainingSession)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.date >= start,
        )
        .order_by(TrainingSession.date.desc())
    )
    if end:
        query = query.where(TrainingSession.date <= end)
    result = await db.execute(query)
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
    exercise_name: str | None = None,
    days: int = 90,
    date_from: date | None = None,
    date_to: date | None = None,
    muscle_group: str | None = None,
) -> dict:
    """Get weight progression, broadened to handle generic keywords.

    Resolution order:
      1. If exercise_name is a known alias / exact name (and no muscle_group
         filter), behave like the original single-exercise lookup.
      2. Otherwise expand via search_exercises(query, muscle_group).
      3. If nothing matches AND exercise_name was given, fall back to
         freeform text match on SessionExercise.exercise_name — preserves
         lookup for user-logged names that aren't in the seeded catalogue.

    Every per-session entry carries `session_type` so the LLM can say
    "X kg 教練課" without a second query.
    """
    if not (exercise_name or muscle_group):
        # This tool needs an exercise_name or muscle_group to return anything.
        # Called with only a date range it would emit a bare empty list, which
        # the LLM tends to misread as "the user has no training data" and then
        # tells the user so. Return an explicit hint to redirect the caller.
        return {
            "query": None,
            "matched_exercises": [],
            "period_days": days,
            "exercises": [],
            "hint": (
                "No exercise_name or muscle_group given — this tool returns "
                "nothing without one. For an OVERALL review use "
                "query_personal_records (no filter returns ALL of the user's "
                "PRs) or query_training_detail. An empty result here does NOT "
                "mean the user has no records; do not tell them so."
            ),
        }

    matched: list[Exercise] = []
    if exercise_name and not muscle_group:
        exact = await resolve_exercise(db, exercise_name)
        if exact:
            matched = [exact]
    if not matched:
        matched = await search_exercises(
            db, query=exercise_name, muscle_group=muscle_group
        )

    start, end = window_dates(days, date_from, date_to)

    base_query = (
        select(SessionExercise, TrainingSession)
        .join(TrainingSession, SessionExercise.session_id == TrainingSession.id)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.date >= start,
        )
        .order_by(TrainingSession.date.asc())
    )
    if end:
        base_query = base_query.where(TrainingSession.date <= end)

    async def _rows_for_exercise(exercise: Exercise | None) -> list[dict]:
        q = base_query
        if exercise is not None:
            q = q.where(SessionExercise.exercise_id == exercise.id)
        else:
            assert exercise_name is not None
            q = q.where(SessionExercise.exercise_name == exercise_name)
        result = await db.execute(q)
        pairs = result.all()

        sessions_data = []
        for se, sess in pairs:
            sets_result = await db.execute(
                select(ExerciseSet).where(ExerciseSet.session_exercise_id == se.id)
            )
            sets_display = [_format_set_compact(es) for es in sets_result.scalars().all()]
            sessions_data.append(
                {
                    "date": sess.date.isoformat(),
                    "session_type": sess.session_type,
                    "sets": sets_display,
                }
            )
        return sessions_data

    # Multi-match path (and single-match — we always populate the new shape).
    exercises_block: list[dict] = []
    matched_names: list[str] = []
    if matched:
        for ex in matched:
            sessions_data = await _rows_for_exercise(ex)
            matched_names.append(ex.name_zh)
            exercises_block.append(
                {
                    "exercise": ex.name_zh,
                    "total_sessions": len(sessions_data),
                    "sessions": sessions_data,
                }
            )
    elif exercise_name:
        # Freeform text fallback for user-logged exercises not in catalogue.
        sessions_data = await _rows_for_exercise(None)
        if sessions_data:
            matched_names.append(exercise_name)
            exercises_block.append(
                {
                    "exercise": exercise_name,
                    "total_sessions": len(sessions_data),
                    "sessions": sessions_data,
                }
            )

    response: dict = {
        "query": exercise_name,
        "muscle_group": muscle_group,
        "matched_exercises": matched_names,
        "period_days": days,
        "exercises": exercises_block,
    }

    # Legacy single-exercise shape so callers / prompts that read `exercise`
    # and `progression` keep working unchanged.
    if len(exercises_block) == 1:
        only = exercises_block[0]
        response["exercise"] = only["exercise"]
        response["total_sessions"] = only["total_sessions"]
        response["progression"] = [
            {
                "date": s["date"],
                "session_type": s["session_type"],
                "sets": s["sets"],
            }
            for s in only["sessions"]
        ]
    return response


async def get_personal_records(
    db: AsyncSession,
    user_id: int,
    exercise_name: str | None = None,
    muscle_group: str | None = None,
) -> list[dict]:
    """List PRs, fuzzy-matched by exercise_name / muscle_group.

    Each row includes the session_type ('self_training' / 'coach' / 'other')
    on the achieved_date — so a single reply can say "X kg, 教練課, YYYY-MM-DD".
    """
    allowed_ids: set[int] | None = None
    if exercise_name or muscle_group:
        matches = await search_exercises(
            db, query=exercise_name, muscle_group=muscle_group
        )
        allowed_ids = {ex.id for ex in matches}
        if not allowed_ids:
            return []

    query = (
        select(PersonalRecord)
        .where(PersonalRecord.user_id == user_id)
        .order_by(PersonalRecord.achieved_date.desc())
    )
    if allowed_ids is not None:
        query = query.where(PersonalRecord.exercise_id.in_(allowed_ids))
    result = await db.execute(query)
    records = result.scalars().all()
    if not records:
        return []

    # Batch the (date -> session_type) lookup so we don't issue one SELECT per PR.
    achieved_dates = {pr.achieved_date for pr in records}
    sess_result = await db.execute(
        select(TrainingSession.date, TrainingSession.session_type)
        .where(
            TrainingSession.user_id == user_id,
            TrainingSession.date.in_(achieved_dates),
        )
    )
    session_type_by_date: dict[date, str] = {row[0]: row[1] for row in sess_result.all()}

    prs = []
    for pr in records:
        exercise = await db.get(Exercise, pr.exercise_id)
        if not exercise:
            continue
        prs.append(
            {
                "exercise": exercise.name_zh,
                "best": pr.weight_display or f"{pr.best_weight_kg}kg",
                "date": pr.achieved_date.isoformat(),
                "session_type": session_type_by_date.get(pr.achieved_date),
                "next_target_kg": pr.next_target_kg,
            }
        )

    return prs


async def get_exercise_catalog(
    db: AsyncSession,
    user_id: int,
    *,
    query: str | None = None,
    muscle_group: str | None = None,
    movement_pattern: str | None = None,
) -> dict:
    """Cheap directory lookup: which exercises match X, and has the user logged them?

    No ExerciseSet rows pulled — this is for the LLM to enumerate candidates
    before drilling in with query_exercise_progression / query_personal_records.
    """
    matches = await search_exercises(
        db, query=query, muscle_group=muscle_group, movement_pattern=movement_pattern
    )
    if not matches:
        return {
            "query": query,
            "muscle_group": muscle_group,
            "movement_pattern": movement_pattern,
            "matched": [],
        }

    match_ids = [ex.id for ex in matches]

    # PR map (one query for all matched exercises).
    pr_result = await db.execute(
        select(PersonalRecord).where(
            PersonalRecord.user_id == user_id,
            PersonalRecord.exercise_id.in_(match_ids),
        )
    )
    pr_by_ex: dict[int, PersonalRecord] = {pr.exercise_id: pr for pr in pr_result.scalars().all()}

    # Last logged date per exercise — single query, then bucket in Python.
    last_logged_result = await db.execute(
        select(
            SessionExercise.exercise_id,
            func.max(TrainingSession.date),
        )
        .join(TrainingSession, SessionExercise.session_id == TrainingSession.id)
        .where(
            TrainingSession.user_id == user_id,
            SessionExercise.exercise_id.in_(match_ids),
        )
        .group_by(SessionExercise.exercise_id)
    )
    last_logged_by_ex: dict[int, date] = {row[0]: row[1] for row in last_logged_result.all()}

    # Aliases + primary muscle names (one query each, then group).
    alias_result = await db.execute(
        select(ExerciseAlias.exercise_id, ExerciseAlias.alias).where(
            ExerciseAlias.exercise_id.in_(match_ids)
        )
    )
    aliases_by_ex: dict[int, list[str]] = {}
    for ex_id, alias in alias_result.all():
        aliases_by_ex.setdefault(ex_id, []).append(alias)

    muscle_result = await db.execute(
        select(ExerciseMuscle.exercise_id, MuscleGroup.name_zh, ExerciseMuscle.is_primary)
        .join(MuscleGroup, ExerciseMuscle.muscle_group_id == MuscleGroup.id)
        .where(ExerciseMuscle.exercise_id.in_(match_ids))
    )
    primary_by_ex: dict[int, list[str]] = {}
    secondary_by_ex: dict[int, list[str]] = {}
    for ex_id, mg_name_zh, is_primary in muscle_result.all():
        bucket = primary_by_ex if is_primary else secondary_by_ex
        bucket.setdefault(ex_id, []).append(mg_name_zh)

    catalog: list[dict] = []
    for ex in matches:
        pr = pr_by_ex.get(ex.id)
        last_logged = last_logged_by_ex.get(ex.id)
        catalog.append(
            {
                "exercise": ex.name_zh,
                "name_en": ex.name,
                "aliases": aliases_by_ex.get(ex.id, []),
                "primary_muscles": primary_by_ex.get(ex.id, []),
                "secondary_muscles": secondary_by_ex.get(ex.id, []),
                "movement_pattern": ex.movement_pattern,
                "has_pr": pr is not None,
                "best": pr.weight_display if pr else None,
                "best_date": pr.achieved_date.isoformat() if pr else None,
                "last_logged_date": last_logged.isoformat() if last_logged else None,
            }
        )

    return {
        "query": query,
        "muscle_group": muscle_group,
        "movement_pattern": movement_pattern,
        "matched": catalog,
    }
