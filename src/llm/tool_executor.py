"""Dispatch LLM tool calls to service functions."""

import json
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from src.services import body_comp, cardio, condition, profile, recommender, workout
from src.utils.time import today

logger = logging.getLogger(__name__)


async def execute_tool(
    db: AsyncSession,
    user_id: int,
    tool_name: str,
    arguments: dict,
) -> str:
    try:
        handler = _HANDLERS.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        result = await handler(db, user_id, arguments)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": f"Failed to execute {tool_name}"})


async def _log_strength_training(db: AsyncSession, user_id: int, args: dict) -> dict:
    training_date = today()
    if args.get("date"):
        training_date = date.fromisoformat(args["date"])

    session, is_new = await workout.get_or_create_session(
        db, user_id, training_date, args.get("session_type", "self_training")
    )

    if args.get("session_notes"):
        session.notes = args["session_notes"]

    results = await workout.record_exercises(db, user_id, session.id, args.get("exercises", []))

    return {
        "session_id": session.id,
        "date": training_date.isoformat(),
        "session_type": session.session_type,
        "is_new_session": is_new,
        "exercises": results,
    }


async def _log_user_condition(db: AsyncSession, user_id: int, args: dict) -> dict:
    exercise_id = None
    exercise_display = None
    if args.get("exercise_name"):
        exercise = await workout.resolve_exercise(db, args["exercise_name"])
        if exercise:
            exercise_id = exercise.id
            exercise_display = exercise.name_zh

    cond = await condition.add_condition(
        db,
        user_id=user_id,
        category=args["category"],
        description=args["description"],
        action_item=args.get("action_item"),
        exercise_id=exercise_id,
    )
    result: dict = {"condition_id": cond.id, "status": "recorded"}
    if exercise_display:
        result["exercise"] = exercise_display
    return result


async def _resolve_user_condition(db: AsyncSession, user_id: int, args: dict) -> dict:
    ok = await condition.resolve_condition(db, user_id, args["condition_id"])
    if ok:
        return {"status": "resolved", "condition_id": args["condition_id"]}
    return {"status": "not_found", "condition_id": args["condition_id"]}


async def _update_user_profile(db: AsyncSession, user_id: int, args: dict) -> dict:
    result = await profile.update_profile(db, user_id, **args)
    return result


async def _query_personal_records(db: AsyncSession, user_id: int, args: dict) -> dict:
    prs = await workout.get_personal_records(db, user_id, args.get("exercise_name"))
    return {"personal_records": prs}


async def _query_training_history(db: AsyncSession, user_id: int, args: dict) -> dict:
    days = args.get("days", 7)
    history = await workout.get_training_history(db, user_id, days)
    return {"sessions": history}


async def _query_training_detail(db: AsyncSession, user_id: int, args: dict) -> dict:
    target_date = None
    if args.get("date"):
        target_date = date.fromisoformat(args["date"])
    days = args.get("days", 7)
    detail = await workout.get_training_detail(db, user_id, days, target_date)
    return {"sessions": detail}


async def _query_exercise_progression(db: AsyncSession, user_id: int, args: dict) -> dict:
    days = args.get("days", 90)
    return await workout.get_exercise_progression(db, user_id, args["exercise_name"], days)


async def _query_conditions(db: AsyncSession, user_id: int, args: dict) -> dict:
    conditions = await condition.get_active_conditions(db, user_id)
    return {"conditions": conditions}


async def _query_exercise_notes(db: AsyncSession, user_id: int, args: dict) -> dict:
    exercise = await workout.resolve_exercise(db, args["exercise_name"])
    if not exercise:
        return {"notes": [], "message": f"Exercise '{args['exercise_name']}' not found"}
    notes = await condition.get_exercise_notes(db, user_id, exercise.id)
    return {"exercise": exercise.name_zh, "notes": notes}


async def _log_cardio(db: AsyncSession, user_id: int, args: dict) -> dict:
    training_date = today()
    if args.get("date"):
        training_date = date.fromisoformat(args["date"])

    result = await cardio.log_cardio(
        db,
        user_id=user_id,
        training_date=training_date,
        cardio_type=args["cardio_type"],
        duration_min=args.get("duration_min"),
        incline=args.get("incline"),
        speed_kmh=args.get("speed_kmh"),
        resistance=args.get("resistance"),
        distance_km=args.get("distance_km"),
        max_heart_rate=args.get("max_heart_rate"),
        avg_heart_rate=args.get("avg_heart_rate"),
        calories=args.get("calories"),
        notes=args.get("notes"),
    )
    return result


async def _log_body_composition(db: AsyncSession, user_id: int, args: dict) -> dict:
    measurement_date = today()
    if args.get("date"):
        measurement_date = date.fromisoformat(args["date"])

    result = await body_comp.log_body_composition(
        db,
        user_id=user_id,
        measurement_date=measurement_date,
        body_fat_pct=args.get("body_fat_pct"),
        weight_kg=args.get("weight_kg"),
        muscle_mass_kg=args.get("muscle_mass_kg"),
        notes=args.get("notes"),
    )
    return result


async def _query_body_composition(db: AsyncSession, user_id: int, args: dict) -> dict:
    days = args.get("days", 90)
    summary = await body_comp.get_body_composition_summary(db, user_id, days)
    history = await body_comp.get_body_composition_history(db, user_id, days)
    return {"summary": summary, "records": history}


async def _query_cardio_progress(db: AsyncSession, user_id: int, args: dict) -> dict:
    days = args.get("days", 30)
    cardio_type = args.get("cardio_type")
    summary = await cardio.get_cardio_summary(db, user_id, days, cardio_type)
    history = await cardio.get_cardio_history(db, user_id, days, cardio_type)
    return {"summary": summary, "records": history}


async def _update_daily_plan(db: AsyncSession, user_id: int, args: dict) -> dict:
    result = await recommender.update_daily_plan(
        db, user_id, args["user_plan"], args["user_response"]
    )
    return result  # type: ignore[return-value]


_HANDLERS = {
    "log_strength_training": _log_strength_training,
    "log_user_condition": _log_user_condition,
    "resolve_user_condition": _resolve_user_condition,
    "update_user_profile": _update_user_profile,
    "query_personal_records": _query_personal_records,
    "query_training_history": _query_training_history,
    "query_training_detail": _query_training_detail,
    "query_exercise_progression": _query_exercise_progression,
    "query_conditions": _query_conditions,
    "query_exercise_notes": _query_exercise_notes,
    "log_cardio": _log_cardio,
    "log_body_composition": _log_body_composition,
    "query_body_composition": _query_body_composition,
    "query_cardio_progress": _query_cardio_progress,
    "update_daily_plan": _update_daily_plan,
}
