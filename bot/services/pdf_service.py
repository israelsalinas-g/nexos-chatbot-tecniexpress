from bot.services import supabase_service
from bot.utils.formatters import format_manual_result


def search_and_format(parsed: dict) -> str | None:
    """
    Busca en manuales PDF indexados y devuelve un mensaje formateado
    si se encuentran resultados, o None si no hay nada.
    """
    results = supabase_service.search_manual_index(parsed)
    if not results:
        return None

    return format_manual_result(results[0], parsed)
