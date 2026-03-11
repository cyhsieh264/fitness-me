from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import DailyInteraction
from src.services import condition, profile, workout
from src.utils.time import timestamp, today


async def build_recommendation_context(
    db: AsyncSession,
    user_id: int,
) -> str:
    """Build context string for daily recommendation (~800 tokens)."""
    current_date = today()
    weekday = current_date.strftime("%A")

    parts = [f"Today: {weekday} ({current_date.isoformat()})"]

    history = await workout.get_training_history(db, user_id, days=7)
    if history:
        parts.append("Recent training (last 7 days):")
        for s in history:
            exercises = ", ".join(s["exercises"])
            parts.append(f"  {s['date']} ({s['session_type']}): {exercises}")
    else:
        parts.append("No training in the last 7 days.")

    conditions = await condition.get_active_conditions(db, user_id)
    if conditions:
        parts.append("Active conditions:")
        for c in conditions[:5]:
            parts.append(f"  [{c['category']}] {c['description']}")

    profile_data = await profile.get_profile_summary(db, user_id)
    if profile_data.get("fitness_goals"):
        parts.append(f"Goals: {profile_data['fitness_goals']}")
    if profile_data.get("training_habit"):
        parts.append(f"Habit: {profile_data['training_habit']}")

    return "\n".join(parts)


async def get_pending_daily_interaction(
    db: AsyncSession,
    user_id: int,
) -> DailyInteraction | None:
    """Get today's unanswered daily interaction, if any."""
    result = await db.execute(
        select(DailyInteraction).where(
            DailyInteraction.user_id == user_id,
            DailyInteraction.date == today(),
            DailyInteraction.push_sent_at.isnot(None),
            DailyInteraction.responded_at.is_(None),
        )
    )
    found: DailyInteraction | None = result.scalar_one_or_none()
    return found


async def update_daily_plan(
    db: AsyncSession,
    user_id: int,
    user_plan: str,
    user_response: str,
) -> dict[str, object]:
    """Record user's reply to daily push. Returns recommendation context if self_training."""
    interaction = await get_pending_daily_interaction(db, user_id)
    if not interaction:
        return {"status": "no_pending_push"}

    interaction.user_plan = user_plan
    interaction.user_response = user_response
    interaction.responded_at = timestamp()

    result: dict[str, object] = {
        "status": "recorded",
        "user_plan": user_plan,
    }

    if user_plan == "self_training":
        context = await build_recommendation_context(db, user_id)
        result["recommendation_context"] = context

    return result


async def save_bot_suggestion(
    db: AsyncSession,
    user_id: int,
    suggestion: str,
) -> None:
    """Save bot's recommendation to today's daily interaction."""
    result = await db.execute(
        select(DailyInteraction).where(
            DailyInteraction.user_id == user_id,
            DailyInteraction.date == today(),
            DailyInteraction.responded_at.isnot(None),
        )
    )
    interaction: DailyInteraction | None = result.scalar_one_or_none()
    if interaction:
        interaction.bot_suggestion = suggestion
