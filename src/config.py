from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LINE Bot
    line_channel_secret: str
    line_channel_access_token: str

    # LLM
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    llm_model: str = "gemini/gemini-2.0-flash"

    # Database
    database_url: str = "sqlite+aiosqlite:///data/fitness.db"

    # App
    allowed_user_ids: str = ""
    timezone: str = "Asia/Taipei"
    base_url: str = ""
    admin_api_key: str = ""

    # Storage
    storage_provider: str = "local"
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_bucket: str = "fitness-images"

    @property
    def allowed_user_id_list(self) -> list[str]:
        if not self.allowed_user_ids:
            return []
        return [uid.strip() for uid in self.allowed_user_ids.split(",") if uid.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
