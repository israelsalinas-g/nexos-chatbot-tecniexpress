import logging
from bot.services import telegram_service

logger = logging.getLogger(__name__)


def handle_photo(chat_id: int, _photos: list[dict], _caption: str | None) -> None:
    """Búsqueda por imagen en pausa — solicita descripción en texto."""
    telegram_service.send_message(
        chat_id,
        "📷 La búsqueda por imagen está temporalmente en pausa.\n\n"
        "Describe el repuesto en texto. Ejemplos:\n"
        "• <code>Actuador Whirlpool</code>\n"
        "• <code>Banda secadora Mabe</code>\n"
        "• <code>Elemento calefactor LG estufa</code>\n"
        "• <code>WPW10006355</code> (SKU o N° de parte)\n\n"
        "¿Qué repuesto necesitas?",
    )
