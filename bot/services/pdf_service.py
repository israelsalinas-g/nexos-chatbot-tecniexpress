from bot.services import supabase_service, claude_service
from bot.utils.formatters import format_manual_result


def search_and_format(parsed: dict) -> dict | None:
    """
    Busca en manuales PDF indexados, extrae info con Claude y devuelve
    un diccionario con el mensaje formateado y opcionalmente una imagen.
    """
    results = supabase_service.search_manual_index(parsed)
    if not results:
        return None

    # Tomamos el mejor fragmento del manual
    best_match = results[0]
    excerpt = best_match.get("excerpt", "")
    query = f"{parsed.get('part', '')} {parsed.get('brand', '')} {parsed.get('model', '')}".strip()

    # Usar Claude para extraer el N° de parte exacto
    try:
        extraction = claude_service.analyze_manual(excerpt, query)
        if extraction.get("found"):
            best_match["part_number"] = extraction.get("part_number")
            best_match["part_name"] = extraction.get("part_name")
    except Exception:
        pass # Fallback al excerpt crudo

    # Si tenemos un N° de parte, intentar buscar la imagen en la BD
    image_url = None
    if best_match.get("part_number"):
        try:
            # Búsqueda exacta por part_number en la tabla products
            products, _ = supabase_service.search_products({"search_terms": [best_match["part_number"]]})
            if products:
                image_url = products[0].get("image_url")
        except Exception:
            pass

    return {
        "text": format_manual_result(best_match, parsed),
        "image_url": image_url
    }
