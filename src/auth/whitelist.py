from src.config import settings


def is_user_allowed(line_user_id: str) -> bool:
    allowed = settings.allowed_user_id_list
    if not allowed:
        return True
    return line_user_id in allowed
