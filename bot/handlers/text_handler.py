from bot.services import claude_service, supabase_service, telegram_service, pdf_service
from bot.utils.formatters import (
    format_quote_response,
    format_no_results,
    format_needs_clarification,
)


def handle_text(chat_id: int, text: str) -> None:
    session = supabase_service.get_session(chat_id)
    state = session["state"]
    context = session["context"]

    telegram_service.send_typing(chat_id)

    # Si el usuario está respondiendo una solicitud de aclaración
    if state == "awaiting_brand":
        context["brand"] = text.strip()
        _run_search(chat_id, context)
        return

    if state == "awaiting_model":
        context["model"] = text.strip()
        _run_search(chat_id, context)
        return

    if state == "awaiting_part":
        context["part"] = text.strip()
        context.setdefault("search_terms", [text.strip()])
        _run_search(chat_id, context)
        return

    # Consulta nueva: parsear con Claude
    try:
        parsed = claude_service.parse_text_query(text)
    except Exception as e:
        print(f"[text_handler] Error Claude: {e}")
        telegram_service.send_message(
            chat_id,
            "⚠️ Tuve un problema procesando tu consulta. Por favor intenta de nuevo.",
        )
        return

    # Combinar con contexto previo si lo hay (sesiones encadenadas)
    for field in ("brand", "model", "part", "search_terms", "appliance_type"):
        if parsed.get(field) and not context.get(field):
            context[field] = parsed[field]
        elif parsed.get(field):
            context[field] = parsed[field]

    # Verificar si hay suficiente información para buscar
    if not context.get("part") and not context.get("search_terms"):
        supabase_service.save_session(chat_id, "awaiting_part", context)
        telegram_service.send_message(
            chat_id,
            format_needs_clarification(["part"], context),
        )
        return

    _run_search(chat_id, context)


def _run_search(chat_id: int, context: dict) -> None:
    """Ejecuta la búsqueda y envía respuesta al usuario."""
    products = supabase_service.search_products(context)

    if products:
        supabase_service.clear_session(chat_id)
        telegram_service.send_message(chat_id, format_quote_response(products, context))
        return

    # Fallback: buscar en manuales
    manual_msg = pdf_service.search_and_format(context)
    if manual_msg:
        supabase_service.clear_session(chat_id)
        telegram_service.send_message(chat_id, manual_msg)
        return

    # Sin resultados: pedir más información si faltan datos
    missing = []
    if not context.get("brand"):
        missing.append("brand")
    elif not context.get("model"):
        missing.append("model")

    if missing:
        new_state = f"awaiting_{missing[0]}"
        supabase_service.save_session(chat_id, new_state, context)
        telegram_service.send_message(
            chat_id,
            format_needs_clarification(missing, context),
        )
    else:
        supabase_service.clear_session(chat_id)
        telegram_service.send_message(chat_id, format_no_results(context))
