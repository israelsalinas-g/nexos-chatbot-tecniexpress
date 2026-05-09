import hmac
import logging
from contextlib import asynccontextmanager

# pyrefly: ignore [missing-import]
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException, Response
try:
    # pyrefly: ignore [missing-import]
    from fastapi.responses import JSONResponse
except ImportError:
    # pyrefly: ignore [missing-import]
    from starlette.responses import JSONResponse

from bot.config import TELEGRAM_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN, APP_URL
from bot.services import telegram_service

print("🚀 Iniciando servidor FastAPI...")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Bot iniciando — pre-cargando modelo CLIP...")
    try:
        from bot.services import clip_service  # dispara carga del modelo al inicio
        logger.info("Modelo CLIP listo.")
    except Exception as e:
        logger.warning(f"CLIP no disponible: {e}. Búsqueda visual usará Claude como fallback.")
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
    logger.info(f"Webhook recibido: {update}")
    background_tasks.add_task(_process_update, update)


    return Response(status_code=200)


@app.get("/setup-webhook")

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


@app.post("/admin/populate-embeddings")
async def populate_embeddings(request: Request, background_tasks: BackgroundTasks):
    """
    Genera embeddings CLIP para todas las imágenes del catálogo que no los tengan.
    Requiere header: X-Admin-Token igual a TELEGRAM_WEBHOOK_SECRET.
    Corre en background para no bloquear la respuesta.
    """
    token = request.headers.get("X-Admin-Token", "")
    if not hmac.compare_digest(token, TELEGRAM_WEBHOOK_SECRET):
        raise HTTPException(status_code=403, detail="Token inválido")

    background_tasks.add_task(_run_populate_embeddings)
    return {"status": "iniciado", "message": "Poblando embeddings en background. Revisa los logs."}


def _run_populate_embeddings() -> None:
    """Genera embeddings CLIP para todas las imágenes del catálogo sin embedding."""
    import time
    # pyrefly: ignore [missing-import]
    import httpx
    from bot.services import clip_service, supabase_service

    logger.info("[populate] Iniciando generación de embeddings CLIP...")

    try:
        r = supabase_service._supabase.table("product_images").select("id, product_id, url").execute()
        images = r.data or []
    except Exception as e:
        logger.error(f"[populate] Error leyendo product_images: {e}")
        return

    try:
        r2 = supabase_service._supabase.table("product_image_embeddings").select("product_image_id").execute()
        existing = {row["product_image_id"] for row in (r2.data or [])}
    except Exception as e:
        logger.error(f"[populate] Error leyendo embeddings existentes: {e}")
        existing = set()

    to_process = [img for img in images if img["id"] not in existing]
    logger.info(f"[populate] {len(to_process)} imágenes a procesar (de {len(images)} totales).")

    ok = errors = skipped = 0
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TecniExpressBot/1.0)"}

    with httpx.Client(follow_redirects=True, headers=headers, timeout=30) as client:
        for idx, img in enumerate(to_process, 1):
            url = img.get("url", "")
            if not url:
                skipped += 1
                continue
            try:
                resp = client.get(url)
                resp.raise_for_status()
                embedding = clip_service.get_image_embedding(resp.content)
                supabase_service._supabase.table("product_image_embeddings").upsert(
                    {
                        "product_id": img["product_id"],
                        "product_image_id": img["id"],
                        "image_url": url,
                        "embedding": embedding,
                        "model_version": "clip-vit-b-32",
                    },
                    on_conflict="product_image_id",
                ).execute()
                ok += 1
                if idx % 10 == 0:
                    logger.info(f"[populate] Progreso: {idx}/{len(to_process)}")
            except Exception as e:
                logger.error(f"[populate] Error en imagen {img['id']}: {e}")
                errors += 1
            time.sleep(0.2)

    logger.info(f"[populate] Completado — OK: {ok} | Errores: {errors} | Sin URL: {skipped}")


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
