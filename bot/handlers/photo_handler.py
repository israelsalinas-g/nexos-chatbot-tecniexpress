from bot.services import claude_service, supabase_service, telegram_service, pdf_service
from bot.utils.formatters import (
    format_quote_response,
    format_no_results,
    format_needs_clarification,
    format_image_analysis_result,
)

_LABEL_KEYWORDS = {"etiqueta", "placa", "label", "modelo", "model", "especificaciones"}


def handle_photo(chat_id: int, photos: list[dict], caption: str | None) -> None:
    """
    Maneja mensajes con fotografía.
    - Si el caption contiene palabras clave de etiqueta → flujo de lectura de etiqueta
    - De lo contrario → flujo de identificación de repuesto
    """
    telegram_service.send_typing(chat_id)
    session = supabase_service.get_session(chat_id)
    context = session["context"]

    # Determinar tipo de imagen por el caption
    caption_lower = (caption or "").lower()
    is_label = any(kw in caption_lower for kw in _LABEL_KEYWORDS)

    # Descargar la imagen de mayor resolución (último elemento de la lista)
    try:
        best_photo = max(photos, key=lambda p: p.get("width", 0) * p.get("height", 0))
        image_bytes = telegram_service.download_photo(best_photo["file_id"])
    except Exception as e:
        print(f"[photo_handler] Error descargando imagen: {e}")
        telegram_service.send_message(
            chat_id,
            "⚠️ No pude descargar la imagen. Por favor intenta enviarla de nuevo.",
        )
        return

    telegram_service.send_message(
        chat_id,
        "🔍 Analizando imagen, un momento...",
    )

    if is_label:
        _handle_label(chat_id, image_bytes, caption or "", context)
    else:
        _handle_part_photo(chat_id, image_bytes, caption or "", context)


def _handle_label(chat_id: int, image_bytes: bytes, caption: str, context: dict) -> None:
    """Flujo: foto de etiqueta → leer modelo → preguntar repuesto."""
    try:
        label_info = claude_service.read_label(image_bytes)
    except Exception as e:
        print(f"[photo_handler] Error Claude read_label: {e}")
        telegram_service.send_message(
            chat_id,
            "⚠️ No pude analizar la etiqueta. Por favor escribe la marca y modelo del equipo.",
        )
        return

    confidence = label_info.get("confidence", 0)
    brand = label_info.get("brand")
    model = label_info.get("model")

    if confidence < 0.5 or not brand or not model:
        telegram_service.send_message(
            chat_id,
            "⚠️ La etiqueta no está clara. ¿Podrías escribir la <b>marca</b> y <b>modelo</b> del equipo?",
        )
        supabase_service.save_session(chat_id, "awaiting_brand", context)
        return

    # Actualizar contexto con info de la etiqueta
    context.update({"brand": brand, "model": model})

    # Extraer repuesto del caption si lo mencionaron junto a la foto
    part_from_caption = _extract_part_from_text(caption)
    if part_from_caption:
        context.update(part_from_caption)
        _run_search(chat_id, context)
    else:
        # Confirmar equipo y pedir repuesto
        supabase_service.save_session(chat_id, "awaiting_part", context)
        telegram_service.send_message(
            chat_id,
            format_image_analysis_result(label_info, "label"),
        )


def _handle_part_photo(chat_id: int, image_bytes: bytes, caption: str, context: dict) -> None:
    """Flujo: foto de repuesto → identificar → buscar."""
    try:
        part_info = claude_service.identify_part(image_bytes, caption)
    except Exception as e:
        print(f"[photo_handler] Error Claude identify_part: {e}")
        telegram_service.send_message(
            chat_id,
            "⚠️ No pude identificar el repuesto. ¿Puedes describirlo con texto o dar más detalles?",
        )
        return

    confidence = part_info.get("confidence", 0)
    needs_more = part_info.get("needs_more_info", False)

    if confidence < 0.4 or needs_more:
        missing = part_info.get("missing_info", "más información")
        supabase_service.save_session(
            chat_id,
            "awaiting_part",
            {**context, "image_analysis": part_info},
        )
        telegram_service.send_message(
            chat_id,
            f"🔍 Identifiqué un posible repuesto pero necesito {missing}. "
            "¿Puedes dar más detalles o escribir qué necesitas?",
        )
        return

    # Construir contexto de búsqueda desde el análisis de imagen
    part_type = part_info.get("part_type", "")
    search_terms = part_info.get("search_terms") or [part_type]
    possible_brands = part_info.get("possible_brands") or []

    search_context = {
        **context,
        "part": part_type,
        "search_terms": search_terms,
    }

    # Si no hay marca en contexto pero Claude identificó posibles marcas, usarla
    if not search_context.get("brand") and len(possible_brands) == 1:
        search_context["brand"] = possible_brands[0]

    telegram_service.send_message(
        chat_id,
        format_image_analysis_result(part_info, "part"),
    )

    _run_search(chat_id, search_context)


def _run_search(chat_id: int, context: dict) -> None:
    from bot.services import supabase_service as _supa

    products = _supa.search_products(context)

    if products:
        _supa.clear_session(chat_id)
        telegram_service.send_message(chat_id, format_quote_response(products, context))
        return

    manual_msg = pdf_service.search_and_format(context)
    if manual_msg:
        _supa.clear_session(chat_id)
        telegram_service.send_message(chat_id, manual_msg)
        return

    missing = []
    if not context.get("brand"):
        missing.append("brand")
    elif not context.get("model"):
        missing.append("model")

    if missing:
        new_state = f"awaiting_{missing[0]}"
        _supa.save_session(chat_id, new_state, context)
        telegram_service.send_message(
            chat_id,
            format_needs_clarification(missing, context),
        )
    else:
        _supa.clear_session(chat_id)
        telegram_service.send_message(chat_id, format_no_results(context))


def _extract_part_from_text(text: str) -> dict | None:
    """Intenta extraer el repuesto de un texto corto (caption)."""
    if not text or len(text) < 5:
        return None
    try:
        from bot.services import claude_service as _cs
        parsed = _cs.parse_text_query(text)
        if parsed.get("part"):
            return {
                "part": parsed["part"],
                "search_terms": parsed.get("search_terms", []),
            }
    except Exception:
        pass
    return None
