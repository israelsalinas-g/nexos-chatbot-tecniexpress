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

def search_by_code(code: str) -> tuple[list[dict], list[str]]:
    """Búsqueda exacta por SKU o N° de parte."""
    try:
        r = _supabase.rpc("search_products_fts", {
            "p_query": code.strip(),
            "p_brand_name": None,
            "p_limit": 5,
        }).execute()
        if r.data:
            return r.data, ["code"]
    except Exception as e:
        print(f"[supabase] Error search_by_code: {e}")
    return [], []


def search_products(parsed: dict) -> tuple[list[dict], list[str]]:
    """
    Búsqueda en 3 etapas:
    1. FTS por nombre/SKU/part_number (RPC)
    2. Compatibilidad por modelo de equipo (RPC)
    3. ILIKE palabra por palabra como último recurso

    Retorna (productos deduplicados max 5, lista de fuentes que encontraron resultados).
    """
    results_by_id: dict[str, dict] = {}
    sources: list[str] = []

    search_terms = parsed.get("search_terms") or []
    part = parsed.get("part") or ""
    brand = parsed.get("brand")
    model = parsed.get("model")

    # Búsqueda directa por código si parece un SKU (tiene dígitos + letras)
    code = parsed.get("code") or ""
    if code:
        code_results, code_sources = search_by_code(code)
        for product in code_results:
            results_by_id[product["id"]] = product
        sources.extend(code_sources)

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

    # Etapa 3: ILIKE fallback si FTS no devolvió nada
    if not results_by_id and fts_query.strip():
        try:
            words = [w for w in fts_query.split() if len(w) > 2][:3]
            q = _supabase.table("bot_products_view").select(
                "id, sku, part_number, name_es, description_es, "
                "price_public, price_technician, price_wholesale, stock_quantity, image_url"
            ).eq("is_active", True)
            for w in words:
                q = q.or_(f"name_es.ilike.%{w}%,sku.ilike.%{w}%")

            brand_name_resolved = brand
            if brand:
                brand_res = _supabase.table("brands").select("id, name").ilike(
                    "name", f"%{brand}%"
                ).limit(1).execute()
                if brand_res.data:
                    q = q.eq("brand_id", brand_res.data[0]["id"])
                    brand_name_resolved = brand_res.data[0]["name"]

            r_ilike = q.limit(5).execute()
            if r_ilike.data:
                sources.append("ilike")
                for product in r_ilike.data:
                    if brand_name_resolved:
                        product["brand_name"] = brand_name_resolved
                    results_by_id[product["id"]] = product
        except Exception as e:
            print(f"[supabase] Error ILIKE fallback: {e}")

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

    # Limpiar y preparar términos
    all_terms = list(set(filter(None, [part, brand, model] + search_terms)))
    
    # Identificar posibles números de parte (alfanuméricos largos)
    part_numbers = [t for t in all_terms if any(c.isdigit() for c in t) and any(c.isalpha() for c in t) and len(t) > 4]
    
    # El query principal será el repuesto + modelo
    main_query = " ".join(filter(None, [part, model]))
    
    print(f"[supabase] Manual Search | Main: '{main_query}' | PartNums: {part_numbers}")

    try:
        r = _supabase.rpc("search_manual_index", {
            "p_query": main_query,
            "p_brand": brand or None,
            "p_model": model or None,
            "p_part_numbers": part_numbers
        }).execute()
        print(f"[supabase] Resultados en manuales: {len(r.data) if r.data else 0}")
        return r.data or []
    except Exception as e:
        print(f"[supabase] Error manual_index: {e}")
        return []


# Etiquetas legibles para cada fuente de búsqueda
SOURCE_LABELS: dict[str, str] = {
    "code":   "🗄️ BD · código exacto",
    "fts":    "🗄️ BD · búsqueda por texto",
    "ilike":  "🗄️ BD · búsqueda aproximada",
    "model":  "🗄️ BD · compatibilidad de modelo",
    "manual": "📄 Manuales técnicos PDF",
    "gdrive": "📄 Manuales PDF (Drive)",
    "web":    "🌐 Web fabricante",
}
