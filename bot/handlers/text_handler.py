import logging
import re
from bot.services import claude_service, supabase_service, telegram_service, pdf_service

logger = logging.getLogger(__name__)

from bot.utils.formatters import (
    format_no_results,
    format_manufacturer_web,
    format_brief_welcome,
    format_similar_footer,
)

# Códigos alfanuméricos que no son SKUs de parte
_SKU_STOP = {
    'SKU', 'REF', 'PARTE', 'PRODUCTO', 'LAVADORA', 'SECADORA', 'ESTUFA',
    'MABE', 'SAMSUNG', 'WHIRLPOOL', 'FRIGIDAIRE', 'LG', 'GE', 'ACROS',
}


def handle_text(chat_id: int, text: str) -> None:
    if supabase_service.is_new_user(chat_id):
        telegram_service.send_message(chat_id, format_brief_welcome())

    session = supabase_service.get_session(chat_id)
    state = session["state"]
    context = session["context"]

    telegram_service.send_typing(chat_id)

    if state == "awaiting_brand":
        context["brand"] = text.strip()
        context.setdefault("search_terms", text.split())
        _run_search(chat_id, context)
        return

    if state == "awaiting_model":
        context["model"] = text.strip()
        _run_search(chat_id, context)
        return

    if state == "awaiting_part":
        context["part"] = text.strip()
        context["search_terms"] = text.split()
        _run_search(chat_id, context)
        return

    # Detectar SKU/código de parte (alfanumérico con dígitos)
    potential_codes = re.findall(r'\b[A-Z0-9]{2,10}(?:-[A-Z0-9]{2,10})*\b', text.upper())
    skus = [c for c in potential_codes if c not in _SKU_STOP and any(ch.isdigit() for ch in c)]

    if skus:
        # Búsqueda por código exacto
        context["code"] = skus[0]
        context["part"] = skus[0]
        context["search_terms"] = [skus[0]]
    else:
        # Búsqueda por palabras: se usan exactamente como las escribió el cliente
        # name_es ya incluye marca y modelo (ej: "Banda de secadora Whirlpool")
        context["part"] = text.strip()
        context["search_terms"] = [w for w in text.split() if len(w) >= 2]

    context["raw_text"] = text.strip()
    logger.info(f"[text_handler] Buscando: {context}")
    _run_search(chat_id, context)


def _run_search(chat_id: int, context: dict) -> None:
    """Busca en BD → PDFs → muestra resultados o sugerencias."""
    products, sources, is_exact = supabase_service.search_products(context)

    if products:
        supabase_service.clear_session(chat_id)

        from bot.utils import formatters
        header = formatters.format_quote_header(context, sources)
        telegram_service.send_message(chat_id, header)

        for p in products[:5]:
            caption = formatters.format_product(p)
            image_url = p.get("image_url")
            if image_url:
                try:
                    telegram_service.send_photo(chat_id, image_url, caption)
                except Exception:
                    telegram_service.send_message(chat_id, caption)
            else:
                telegram_service.send_message(chat_id, caption)

        footer = format_similar_footer() if not is_exact else formatters.format_quote_footer()
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
