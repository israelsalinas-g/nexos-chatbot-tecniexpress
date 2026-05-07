import logging
from bot.services import claude_service, supabase_service, telegram_service, pdf_service

logger = logging.getLogger(__name__)

from bot.utils.formatters import (
    format_quote_response,
    format_no_results,
)


def handle_text(chat_id: int, text: str) -> None:
    session = supabase_service.get_session(chat_id)
    state = session["state"]
    context = session["context"]

    telegram_service.send_typing(chat_id)

    # Respuestas a solicitudes de aclaración anteriores
    if state == "awaiting_brand":
        context["brand"] = text.strip()
        context.setdefault("search_terms", [text.strip()])
        _run_search(chat_id, context)
        return

    if state == "awaiting_model":
        context["model"] = text.strip()
        _run_search(chat_id, context)
        return

    if state == "awaiting_part":
        context["part"] = text.strip()
        context["search_terms"] = [text.strip()]
        _run_search(chat_id, context)
        return

    # Consulta nueva: parsear con Claude para extraer brand/model/part
    try:
        parsed = claude_service.parse_text_query(text)
    except Exception as e:
        logger.error(f"[text_handler] Falló Claude, usando texto directo: {e}")
        parsed = {"part": text.strip(), "search_terms": [text.strip()], "confidence": 0.5}

    # Combinar con contexto de sesión previa
    for field in ("brand", "model", "part", "search_terms", "appliance_type"):
        if parsed.get(field):
            context[field] = parsed[field]

    # Si Claude no extrajo nada útil, usar el texto crudo como término de búsqueda
    if not context.get("part") and not context.get("search_terms"):
        context["part"] = text.strip()
        context["search_terms"] = [text.strip()]

    # Siempre buscar primero — nunca pedir información antes de intentar
    _run_search(chat_id, context)


def _run_search(chat_id: int, context: dict) -> None:
    """Busca en BD → PDFs → muestra resultados o sugerencias."""
    products, sources = supabase_service.search_products(context)

    if products:
        supabase_service.clear_session(chat_id)
        telegram_service.send_message(
            chat_id,
            format_quote_response(products, context, sources),
        )
        return

    # Fallback: manuales PDF
    manual_msg = pdf_service.search_and_format(context)
    if manual_msg:
        supabase_service.clear_session(chat_id)
        telegram_service.send_message(chat_id, manual_msg)
        return

    # Sin resultados en ninguna fuente — mostrar mensaje con sugerencias
    supabase_service.clear_session(chat_id)
    telegram_service.send_message(chat_id, format_no_results(context))
