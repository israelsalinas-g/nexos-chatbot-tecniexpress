from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Telegram
    telegram_token: str
    telegram_webhook_url: str

    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Supabase
    supabase_url: str
    supabase_key: str                   # service_role key

    # Google Drive
    google_service_account_json: str    # JSON completo en una sola línea

    # App
    app_env: str = "development"
    debug: bool = False

    # Asesor humano
    advisor_telegram_chat_id: str = ""

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()
