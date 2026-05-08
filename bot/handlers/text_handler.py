import logging
from bot.services import claude_service, supabase_service, telegram_service, pdf_service

logger = logging.getLogger(__name__)

from bot.utils.formatters import (
    format_quote_response,
    format_no_results,
    format_manufacturer_web,
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
    import re
    # Patrón simple para SKUs: Alfanuméricos de 6+ caracteres o con guiones
    potential_codes = re.findall(r'\b[A-Z0-9]{2,10}(?:-[A-Z0-9]{2,10})*\b', text.upper())
    # Filtrar términos comunes que no son SKUs (ej: SKU, REF, PARTE, PRODUCTO)
    STOP_CODES = {'SKU', 'REF', 'PARTE', 'PRODUCTO', 'LAVADORA', 'MABE', 'SAMSUNG', 'WHIRLPOOL', 'LG'}
    skus = [c for c in potential_codes if c not in STOP_CODES and any(char.isdigit() for char in c)]

    try:
        parsed = claude_service.parse_text_query(text)
    except Exception as e:
        logger.error(f"[text_handler] Falló Claude, usando texto directo: {e}")
        parsed = {"part": text.strip(), "search_terms": [text.strip()], "confidence": 0.5}

    if skus:
        parsed["code"] = skus[0]
        parsed["part"] = skus[0]
        parsed["search_terms"] = [skus[0]]

    # Combinar con contexto de sesión previa
    # Si Claude identificó un repuesto nuevo, reemplazamos el anterior para no mezclar "actuador" con "teclado"
    if parsed.get("part") or parsed.get("search_terms"):
        context["part"] = parsed.get("part")
        context["search_terms"] = parsed.get("search_terms")

    for field in ("brand", "model", "appliance_type"):
        if parsed.get(field):
            context[field] = parsed[field]

    # Si después de todo no hay un repuesto claro en el contexto, usamos el texto del usuario
    if not context.get("part") and not context.get("search_terms"):
        context["part"] = text.strip()
        context["search_terms"] = [text.strip()]
    
    # Debug log (opcional, ayuda a ver qué está buscando el bot)
    logger.info(f"[text_handler] Buscando: {context}")

    # Siempre buscar primero — nunca pedir información antes de intentar
    _run_search(chat_id, context)


def _run_search(chat_id: int, context: dict) -> None:
    """Busca en BD → PDFs → muestra resultados o sugerencias."""
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
                    # Si la URL de la imagen falla o es inválida, enviar como texto normal
                    telegram_service.send_message(chat_id, caption)
            else:
                telegram_service.send_message(chat_id, caption)
                
        # Enviar pie de mensaje
        footer = formatters.format_quote_footer()
        telegram_service.send_message(chat_id, footer)
        return

    # Fallback: manuales PDF
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

    # Capa 3: referencia del fabricante vía conocimiento de Claude
    web_text = claude_service.search_manufacturer_web(context)
    if web_text:
        supabase_service.clear_session(chat_id)
        telegram_service.send_message(chat_id, format_manufacturer_web(web_text, context))
        return

    # Sin resultados en ninguna fuente
    # Guardamos el estado en lugar de limpiar la sesión para que recuerde el contexto (ej: el repuesto)
    missing_fields = []
    if not context.get("brand"): missing_fields.append("brand")
    if not context.get("model"): missing_fields.append("model")
    
    if missing_fields:
        if "brand" in missing_fields:
            supabase_service.save_session(chat_id, "awaiting_brand", context)
        elif "model" in missing_fields:
            supabase_service.save_session(chat_id, "awaiting_model", context)
    else:
        # Si ya tiene todo y no encontró nada, sí limpiamos
        supabase_service.clear_session(chat_id)
        
    telegram_service.send_message(chat_id, format_no_results(context))
