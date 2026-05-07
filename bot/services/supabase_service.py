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

def search_products(parsed: dict) -> list[dict]:
    """
    Búsqueda en 3 etapas:
    1. FTS por nombre/SKU/part_number
    2. Compatibilidad por modelo de equipo
    3. Fallback en manuales PDF

    Retorna lista deduplicada, máximo 5 resultados.
    """
    results_by_id: dict[str, dict] = {}

    search_terms = parsed.get("search_terms") or []
    part = parsed.get("part") or ""
    brand = parsed.get("brand")
    model = parsed.get("model")

    fts_query = " ".join(filter(None, [part] + search_terms))

    # Etapa 1: FTS
    if fts_query.strip():
        try:
            r = _supabase.rpc("search_products_fts", {
                "p_query": fts_query,
                "p_brand_name": brand,
                "p_limit": 8,
            }).execute()
            for product in (r.data or []):
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
            for product in (r.data or []):
                pid = product["id"]
                if pid not in results_by_id:
                    results_by_id[pid] = product
                else:
                    # Producto aparece en ambas etapas → prioridad alta
                    results_by_id[pid]["_double_match"] = True
        except Exception as e:
            print(f"[supabase] Error compatibility: {e}")

    # Ordenar: doble match primero, luego por rank si existe
    sorted_results = sorted(
        results_by_id.values(),
        key=lambda p: (p.get("_double_match", False), p.get("rank", 0)),
        reverse=True,
    )

    return sorted_results[:5]


def search_manual_index(parsed: dict) -> list[dict]:
    """Busca en manuales PDF indexados como fallback."""
    search_terms = parsed.get("search_terms") or []
    part = parsed.get("part") or ""
    fts_query = " ".join(filter(None, [part] + search_terms))

    if not fts_query.strip():
        return []

    try:
        r = _supabase.rpc("search_manual_index", {
            "p_query": fts_query,
            "p_brand": parsed.get("brand"),
            "p_model": parsed.get("model"),
        }).execute()
        return r.data or []
    except Exception as e:
        print(f"[supabase] Error manual_index: {e}")
        return []
