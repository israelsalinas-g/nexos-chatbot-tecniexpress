from datetime import datetime, timezone, timedelta
from supabase import create_client, Client
from bot.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SESSION_TTL_MINUTES

_supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ─────────────────────────────────────────────────────────────
# Sesiones de conversación
# ─────────────────────────────────────────────────────────────

def get_session(chat_id: int) -> dict:
    """Devuelve la sesión activa o un estado idle si expiró."""
    result = (
        _supabase.table("telegram_sessions")
        .select("state, context, updated_at")
        .eq("chat_id", chat_id)
        .maybe_single()
        .execute()
    )

    if not result.data:
        return {"state": "idle", "context": {}}

    updated_at = datetime.fromisoformat(result.data["updated_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - updated_at > timedelta(minutes=SESSION_TTL_MINUTES):
        return {"state": "idle", "context": {}}

    return {"state": result.data["state"], "context": result.data["context"]}


def save_session(chat_id: int, state: str, context: dict) -> None:
    _supabase.table("telegram_sessions").upsert(
        {"chat_id": chat_id, "state": state, "context": context},
        on_conflict="chat_id",
    ).execute()


def clear_session(chat_id: int) -> None:
    save_session(chat_id, "idle", {})


# ─────────────────────────────────────────────────────────────
# Búsqueda de productos
# ─────────────────────────────────────────────────────────────

def search_products(parsed: dict) -> tuple[list[dict], list[str]]:
    """
    Búsqueda en 2 etapas en paralelo:
    1. FTS por nombre/SKU/part_number
    2. Compatibilidad por modelo de equipo

    Retorna (productos deduplicados max 5, lista de fuentes que encontraron resultados).
    """
    results_by_id: dict[str, dict] = {}
    sources: list[str] = []

    search_terms = parsed.get("search_terms") or []
    part = parsed.get("part") or ""
    brand = parsed.get("brand")
    model = parsed.get("model")

    fts_query = " ".join(filter(None, [part] + search_terms))

    # Etapa 1: FTS por texto
    if fts_query.strip():
        try:
            r = _supabase.rpc("search_products_fts", {
                "p_query": fts_query,
                "p_brand_name": brand,
                "p_limit": 8,
            }).execute()
            if r.data:
                sources.append("fts")
                for product in r.data:
                    results_by_id[product["id"]] = product
        except Exception as e:
            print(f"[supabase] Error FTS: {e}")

    # Etapa 2: Compatibilidad por modelo
    if model:
        try:
            r = _supabase.rpc("search_products_by_model", {
                "p_model": model,
                "p_brand": brand,
                "p_part_filter": part or None,
                "p_limit": 10,
            }).execute()
            if r.data:
                sources.append("model")
                for product in r.data:
                    pid = product["id"]
                    if pid not in results_by_id:
                        results_by_id[pid] = product
                    else:
                        results_by_id[pid]["_double_match"] = True
        except Exception as e:
            print(f"[supabase] Error compatibility: {e}")

    sorted_results = sorted(
        results_by_id.values(),
        key=lambda p: (p.get("_double_match", False), p.get("rank", 0)),
        reverse=True,
    )

    return sorted_results[:5], sources


def search_manual_index(parsed: dict) -> list[dict]:
    """Busca en manuales PDF indexados como fallback."""
    search_terms = parsed.get("search_terms") or []
    part = parsed.get("part") or ""
    brand = parsed.get("brand") or ""
    model = parsed.get("model") or ""

    # Incluir marca y modelo en el query FTS para mayor cobertura
    fts_query = " ".join(filter(None, [part, brand, model] + search_terms))

    if not fts_query.strip():
        return []

    print(f"[supabase] Buscando en manuales con query: '{fts_query}' | Brand: {parsed.get('brand')} | Model: {parsed.get('model')}")
    try:
        r = _supabase.rpc("search_manual_index", {
            "p_query": fts_query,
            "p_brand": parsed.get("brand"),
            "p_model": parsed.get("model"),
        }).execute()
        print(f"[supabase] Resultados en manuales: {len(r.data) if r.data else 0}")
        return r.data or []
    except Exception as e:
        print(f"[supabase] Error manual_index: {e}")
        return []


# Etiquetas legibles para cada fuente de búsqueda
SOURCE_LABELS: dict[str, str] = {
    "fts":    "🗄️ BD · búsqueda por texto",
    "model":  "🗄️ BD · compatibilidad de modelo",
    "manual": "📄 Manuales técnicos PDF",
    "web":    "🌐 Sitio web del fabricante",
}
