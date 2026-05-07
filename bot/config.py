import os
from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value and not name.startswith("NEXT_PUBLIC_"):
        value = os.getenv(f"NEXT_PUBLIC_{name}")
    
    if not value:
        print(f"CRITICAL: Variable de entorno requerida no configurada: {name}")
        raise RuntimeError(f"Variable de entorno requerida no configurada: {name}")
    return value


TELEGRAM_BOT_TOKEN: str = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_WEBHOOK_SECRET: str = _require("TELEGRAM_WEBHOOK_SECRET")

SUPABASE_URL: str = _require("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: str = _require("SUPABASE_SERVICE_ROLE_KEY")

ANTHROPIC_API_KEY: str = _require("ANTHROPIC_API_KEY")

# Google Drive es opcional — solo se necesita para el script de indexado
GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

APP_URL: str = os.getenv("APP_URL", "")

# Modelo Claude a usar
CLAUDE_MODEL = "claude-3-haiku-20240307"




# Máximo de resultados por búsqueda en el chat
MAX_RESULTS = 5

# Tiempo de expiración de sesión en minutos
SESSION_TTL_MINUTES = 30

SUPPORTED_BRANDS = ["LG", "Samsung", "Mabe", "GE", "Whirlpool", "Frigidaire"]
