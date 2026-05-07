import logging
from bot.services import supabase_service, claude_service
from bot.utils.formatters import format_manual_result

logger = logging.getLogger(__name__)


def search_and_format(parsed: dict) -> dict | None:
    """
    Busca en manuales PDF en 2 pasos:
      1. Google Drive on-demand — busca el PDF del modelo en Drive y extrae texto relevante
      2. manual_index FTS — fallback en manuales pre-indexados en Supabase

    Retorna dict con {text, image_url} o None si no hay resultados en ninguna fuente.
    """
    model = parsed.get("model") or ""
    brand = parsed.get("brand") or ""
    part  = parsed.get("part") or ""
    terms = " ".join(parsed.get("search_terms") or [])
    part_desc = part or terms

    # ── Paso 1: Google Drive on-demand ────────────────────────────────────────
    if model:
        try:
            from bot.services import gdrive_service
            gdrive_result = gdrive_service.search_in_manual(
                brand=brand,
                model=model,
                part_description=part_desc,
                part_type=part or None,
            )
            if gdrive_result.get("found") and gdrive_result.get("relevant_text"):
                logger.info(f"[pdf_service] Encontrado en Drive para {brand} {model}")
                return _format_from_text(gdrive_result["relevant_text"], parsed, source="gdrive")
        except Exception as e:
            logger.warning(f"[pdf_service] Drive no disponible: {e}")

    # ── Paso 2: manual_index FTS en Supabase ──────────────────────────────────
    results = supabase_service.search_manual_index(parsed)
    if not results:
        return None

    best = results[0]
    excerpt = best.get("excerpt", "")
    query = f"{part} {brand} {model}".strip()

    try:
        extraction = claude_service.analyze_manual(excerpt, query)
        if extraction.get("found"):
            best["part_number"] = extraction.get("part_number")
            best["part_name"]   = extraction.get("part_name")
    except Exception:
        pass

    image_url = _try_find_image(best.get("part_number"))
    return {"text": format_manual_result(best, parsed), "image_url": image_url}


def _format_from_text(relevant_text: str, parsed: dict, source: str = "gdrive") -> dict | None:
    """Dado texto relevante de un PDF, usa Claude para extraer N° de parte y formatea."""
    part  = parsed.get("part") or ""
    brand = parsed.get("brand") or ""
    model = parsed.get("model") or ""
    query = f"{part} {brand} {model}".strip()

    manual_data = {
        "brand":        brand,
        "model_prefix": model,
        "excerpt":      relevant_text[:600],
        "source":       source,
    }

    try:
        extraction = claude_service.analyze_manual(relevant_text[:1500], query)
        if extraction.get("found"):
            manual_data["part_number"] = extraction.get("part_number")
            manual_data["part_name"]   = extraction.get("part_name")
    except Exception:
        pass

    image_url = _try_find_image(manual_data.get("part_number"))
    return {"text": format_manual_result(manual_data, parsed), "image_url": image_url}


def _try_find_image(part_number: str | None) -> str | None:
    """Busca la URL de imagen del producto por N° de parte."""
    if not part_number:
        return None
    try:
        products, _ = supabase_service.search_products(
            {"part": part_number, "search_terms": [part_number]}
        )
        if products:
            return products[0].get("image_url")
    except Exception:
        pass
    return None
