from src.config import settings


def is_user_allowed(line_user_id: str) -> bool:
    """Fail closed: an empty whitelist blocks everyone.

    The bot is a public LINE Official Account — anyone can friend it. If
    ALLOWED_USER_IDS were treated as "empty = open", a missing secret or a
    deploy that drops the env var would silently expose the bot (and its
    LLM token budget) to the world. Opening up must be an explicit choice,
    not a side effect of a configuration gap.
    """
    return line_user_id in settings.allowed_user_id_list
