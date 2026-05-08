# pyrefly: ignore [missing-import]
import httpx
from bot.config import TELEGRAM_BOT_TOKEN

_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
_FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"


def _post(endpoint: str, payload: dict) -> dict:
    with httpx.Client(timeout=15) as client:
        resp = client.post(f"{_BASE}/{endpoint}", json=payload)
        resp.raise_for_status()
        return resp.json()


def send_message(chat_id: int, text: str, parse_mode: str = "HTML") -> dict:
    return _post("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    })

def send_photo(chat_id: int, photo_url: str, caption: str = "", parse_mode: str = "HTML") -> dict:
    return _post("sendPhoto", {
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": parse_mode,
    })


def send_typing(chat_id: int) -> None:
    try:
        _post("sendChatAction", {"chat_id": chat_id, "action": "typing"})
    except Exception:
        pass


def download_photo(file_id: str) -> bytes:
    """Descarga la imagen más grande disponible desde Telegram."""
    with httpx.Client(timeout=30) as client:
        # Paso 1: obtener file_path
        resp = client.get(f"{_BASE}/getFile", params={"file_id": file_id})
        resp.raise_for_status()
        file_path = resp.json()["result"]["file_path"]

        # Paso 2: descargar bytes
        img_resp = client.get(f"{_FILE_BASE}/{file_path}")
        img_resp.raise_for_status()
        return img_resp.content


def set_webhook(url: str, secret_token: str) -> dict:
    return _post("setWebhook", {
        "url": url,
        "secret_token": secret_token,
        "allowed_updates": ["message"],
        "drop_pending_updates": True,
    })


def delete_webhook() -> dict:
    return _post("deleteWebhook", {"drop_pending_updates": True})


def get_webhook_info() -> dict:
    with httpx.Client(timeout=10) as client:
        resp = client.get(f"{_BASE}/getWebhookInfo")
        resp.raise_for_status()
        return resp.json()


def download_image_from_url(url: str) -> bytes:
    """Descarga una imagen desde cualquier URL pública."""
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content
