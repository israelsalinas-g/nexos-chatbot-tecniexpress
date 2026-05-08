import logging
from bot.services import claude_service, supabase_service, telegram_service, pdf_service

logger = logging.getLogger(__name__)

from bot.utils.formatters import (
    format_quote_response,
    format_no_results,
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
        logger.error(f"[photo_handler] Falló lectura de etiqueta (Claude): {e}")
        telegram_service.send_message(
            chat_id,
            "⚠️ No pude analizar la foto de la etiqueta. Por favor escribe la <b>marca</b> y <b>modelo</b> de tu equipo manualmente.",
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
    """Flujo: foto de repuesto → identificar → buscar siempre."""
    try:
        part_info = claude_service.identify_part(image_bytes, caption)
    except Exception as e:
        logger.error(f"[photo_handler] Falló identificación visual (Claude): {e}")
        if caption:
            telegram_service.send_message(chat_id, "🔍 No pude analizar la imagen, buscando con tu descripción...")
            _run_search(chat_id, {**context, "part": caption.strip(), "search_terms": [caption.strip()]})
        else:
            telegram_service.send_message(
                chat_id,
                "⚠️ No pude identificar el repuesto. Por favor descríbelo con texto.",
            )
        return

    part_type = part_info.get("part_type", "")
    search_terms = part_info.get("search_terms") or ([part_type] if part_type else [])
    possible_brands = part_info.get("possible_brands") or []
    confidence = part_info.get("confidence", 0)

    # Si Claude no pudo identificar nada útil, pedir descripción
    if not part_type and not search_terms and not caption:
        telegram_service.send_message(
            chat_id,
            "🔍 No pude identificar el repuesto claramente. "
            "¿Podrías describir qué pieza es o agregar un texto al enviar la foto?",
        )
        return

    # Construir contexto: si no hay part_type pero sí caption, usar el caption
    search_context = {
        **context,
        "part": part_type or caption.strip(),
        "search_terms": search_terms or [caption.strip()],
    }
    if not search_context.get("brand") and len(possible_brands) == 1:
        search_context["brand"] = possible_brands[0]

    # Mostrar qué identificó Claude (con nota de confianza si es baja)
    confidence_note = " <i>(identificación aproximada)</i>" if confidence < 0.5 else ""
    if part_type:
        telegram_service.send_message(
            chat_id,
            f"🔍 Identificado: <b>{part_type}</b>{confidence_note}\nBuscando en inventario...",
        )

    _run_search(chat_id, search_context)


def _run_search(chat_id: int, context: dict) -> None:
    products, sources = supabase_service.search_products(context)

    if products:
        supabase_service.clear_session(chat_id)
        
        # Enviar encabezado
        from bot.utils import formatters
        header = formatters.format_quote_header(context, sources)
        telegram_service.send_message(chat_id, header)
        
        # Enviar cada producto individualmente (con foto si existe)
        for p in products[:5]:
            caption = formatters.format_product(p)
            image_url = p.get("image_url")
            
            if image_url:
                try:
                    telegram_service.send_photo(chat_id, image_url, caption)
                except Exception:
                    # Si la URL de la imagen falla, enviar como texto normal
                    telegram_service.send_message(chat_id, caption)
            else:
                telegram_service.send_message(chat_id, caption)
                
        # Enviar pie de mensaje
        footer = formatters.format_quote_footer()
        telegram_service.send_message(chat_id, footer)
        return

    manual_res = pdf_service.search_and_format(context)
    if manual_res:
        supabase_service.clear_session(chat_id)
        text = manual_res["text"]
        image_url = manual_res.get("image_url")

        if image_url:
            telegram_service.send_photo(chat_id, image_url, text)
        else:
            telegram_service.send_message(chat_id, text)
        return

    # Guardamos el estado en lugar de limpiar la sesión para que recuerde el contexto
    missing_fields = []
    if not context.get("brand"): missing_fields.append("brand")
    if not context.get("model"): missing_fields.append("model")
    
    if missing_fields:
        if "brand" in missing_fields:
            supabase_service.save_session(chat_id, "awaiting_brand", context)
        elif "model" in missing_fields:
            supabase_service.save_session(chat_id, "awaiting_model", context)
    else:
        supabase_service.clear_session(chat_id)
        
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
