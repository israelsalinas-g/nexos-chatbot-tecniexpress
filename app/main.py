import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Response
from fastapi.responses import JSONResponse

from bot.config import TELEGRAM_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN, APP_URL
from bot.services import telegram_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Bot iniciando...")
    yield
    logger.info("Bot detenido.")


app = FastAPI(title="Tecni Express Bot", lifespan=lifespan)


@app.get("/")
def root():
    return {"message": "Tecni Express Bot API is running"}


@app.get("/health")

def health():
    return {"status": "ok", "bot": "tecni-express"}


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    # Validar el secret token que Telegram envía en cada webhook
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(secret, TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Invalid secret")

    update = await request.json()

    # Responder a Telegram inmediatamente (requiere < 5s)
    # El procesamiento real ocurre en background
    background_tasks.add_task(_process_update, update)

    return Response(status_code=200)


@app.post("/setup-webhook")
async def setup_webhook():
    """Endpoint de utilidad para registrar el webhook en Telegram."""
    if not APP_URL:
        return JSONResponse(
            {"error": "APP_URL no configurada"},
            status_code=400,
        )
    webhook_url = f"{APP_URL.rstrip('/')}/webhook"
    result = telegram_service.set_webhook(webhook_url, TELEGRAM_WEBHOOK_SECRET)
    return result


@app.get("/webhook-info")
async def webhook_info():
    return telegram_service.get_webhook_info()


def _process_update(update: dict) -> None:
    """Enruta la actualización de Telegram al handler correspondiente."""
    try:
        message = update.get("message")
        if not message:
            return  # Ignorar callbacks y otros tipos por ahora

        chat_id: int = message["chat"]["id"]
        from_user: dict = message.get("from", {})
        user_name: str | None = from_user.get("first_name")

        text: str | None = message.get("text")
        photos: list | None = message.get("photo")
        caption: str | None = message.get("caption")

        # Comandos
        if text and text.startswith("/"):
            _handle_command(chat_id, text, user_name)
            return

        # Foto (con o sin caption)
        if photos:
            from bot.handlers.photo_handler import handle_photo
            handle_photo(chat_id, photos, caption)
            return

        # Texto normal
        if text:
            from bot.handlers.text_handler import handle_text
            handle_text(chat_id, text)
            return

        # Tipo de mensaje no soportado
        telegram_service.send_message(
            chat_id,
            "Por favor envía texto o una imagen. ¿En qué puedo ayudarte?",
        )

    except Exception:
        logger.exception("Error procesando update: %s", update)
        try:
            chat_id = update["message"]["chat"]["id"]
            telegram_service.send_message(
                chat_id,
                "⚠️ Ocurrió un error inesperado. Por favor intenta de nuevo.",
            )
        except Exception:
            pass


def _handle_command(chat_id: int, text: str, user_name: str | None) -> None:
    command = text.split()[0].lower().split("@")[0]  # strip bot username suffix

    if command == "/start":
        from bot.handlers.command_handler import handle_start
        handle_start(chat_id, user_name)
    elif command == "/help" or command == "/ayuda":
        from bot.handlers.command_handler import handle_help
        handle_help(chat_id)
    else:
        telegram_service.send_message(
            chat_id,
            "Comando no reconocido. Usa /help para ver las opciones disponibles.",
        )
