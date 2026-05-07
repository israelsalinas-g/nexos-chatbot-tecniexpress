"""
supabase_service.py — Búsqueda de productos con esquema real de TecniExpress

Columnas reales:
  products: id(uuid), sku, part_number, name_es, name_en, description_es,
            brand_id(uuid), category_id(uuid), compatible_models(array),
            tags(array), price_public, price_technician, stock_quantity,
            is_active, fts (generada con fix_search.sql)
"""
from supabase import create_client, Client
from app.config import settings
from typing import Optional
from datetime import datetime
import logging, json

logger = logging.getLogger(__name__)

def _client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_key)

# ── Caché simple de marcas para no repetir queries ────────────────────────────
_brand_cache: dict = {}

async def _resolve_brand_id(brand_name: str) -> Optional[str]:
    """Convierte nombre de marca ('LG') a UUID."""
    if not brand_name:
        return None
    key = brand_name.strip().upper()
    if key in _brand_cache:
        return _brand_cache[key]
    sb = _client()
    res = sb.table("brands").select("id,name").ilike("name", f"%{brand_name}%").limit(1).execute()
    if res.data:
        uid = res.data[0]["id"]
        _brand_cache[key] = uid
        return uid
    return None

def _fmt(row: dict) -> dict:
    """Normaliza fila de products_full para el bot."""
    stock = row.get("stock_quantity") or 0
    price = row.get("price_public") or 0
    return {
        "id":               row.get("id"),
        "sku":              row.get("sku", ""),
        "part_number":      row.get("part_number", ""),
        "name":             row.get("name_es") or row.get("name_en", "Sin nombre"),
        "description":      row.get("description_es", ""),
        "brand":            row.get("brand_name", ""),
        "category":         row.get("category_name", ""),
        "price":            price,
        "stock":            stock,
        "in_stock":         stock > 0,
        "compatible_models": row.get("compatible_models") or [],
        "tags":              row.get("tags") or [],
    }

# ── Búsqueda 1: por SKU / part_number ────────────────────────────────────────
async def search_by_code(code: str) -> list:
    sb = _client()
    code = code.strip().upper()
    try:
        res = (
            sb.table("products_full").select("*")
            .or_(f"sku.eq.{code},sku.ilike.%{code}%,part_number.eq.{code},part_number.ilike.%{code}%")
            .limit(5).execute()
        )
        return [_fmt(r) for r in (res.data or [])]
    except Exception as e:
        logger.error(f"search_by_code: {e}")
        return []

# ── Búsqueda 2: full-text search + filtro de marca ───────────────────────────
async def search_by_text(query: str, brand_name: Optional[str] = None) -> list:
    sb = _client()
    try:
        # Primero intenta la función RPC (requiere fix_search.sql ejecutado)
        params = {"query_text": query, "max_results": 8}
        if brand_name:
            params["brand_name"] = brand_name
        res = sb.rpc("search_products", params).execute()
        if res.data:
            return [_fmt(r) for r in res.data]
    except Exception:
        pass  # RPC no existe todavía, caer en ILIKE

    # Fallback ILIKE palabra por palabra
    try:
        sb2 = _client()
        words = [w for w in query.split() if len(w) > 2][:3]
        q = sb2.table("products_full").select("*")
        for w in words:
            q = q.ilike("name_es", f"%{w}%")
        if brand_name:
            q = q.ilike("brand_name", f"%{brand_name}%")
        res2 = q.eq("is_active", True).limit(8).execute()
        return [_fmt(r) for r in (res2.data or [])]
    except Exception as e:
        logger.error(f"search_by_text fallback: {e}")
        return []

# ── Búsqueda 3: por modelo en array compatible_models ────────────────────────
async def search_by_model(model: str, brand_name: Optional[str] = None) -> list:
    sb = _client()
    try:
        q = (
            sb.table("products_full").select("*")
            .contains("compatible_models", [model.strip().upper()])
        )
        if brand_name:
            q = q.ilike("brand_name", f"%{brand_name}%")
        res = q.eq("is_active", True).limit(10).execute()
        return [_fmt(r) for r in (res.data or [])]
    except Exception as e:
        logger.error(f"search_by_model: {e}")
        return []

# ── Orquestador principal ─────────────────────────────────────────────────────
async def smart_search(
    query_text: Optional[str] = None,
    brand_name: Optional[str] = None,
    model:      Optional[str] = None,
    code:       Optional[str] = None,
) -> tuple:
    """
    Retorna (lista_productos, método_usado).
    Orden: código exacto → full-text → modelo → fallback.
    """
    if code:
        r = await search_by_code(code)
        if r: return r, "código de parte"

    if query_text:
        r = await search_by_text(query_text, brand_name=brand_name)
        if r: return r, "búsqueda de texto"

    if model:
        r = await search_by_model(model, brand_name=brand_name)
        if r: return r, "modelo compatible"

    # Último recurso: solo ilike en name_es con primera palabra
    if brand_name and query_text:
        sb = _client()
        try:
            first_word = query_text.split()[0]
            res = (
                sb.table("products_full").select("*")
                .ilike("brand_name", f"%{brand_name}%")
                .ilike("name_es", f"%{first_word}%")
                .eq("is_active", True).limit(5).execute()
            )
            if res.data:
                return [_fmt(r) for r in res.data], "búsqueda aproximada"
        except Exception as e:
            logger.error(f"smart_search fallback: {e}")

    return [], "sin_resultados"

# ── Conversaciones ────────────────────────────────────────────────────────────
async def get_conversation(chat_id: str) -> dict:
    sb = _client()
    try:
        res = sb.table("conversations").select("*").eq("chat_id", chat_id).maybe_single().execute()
        if res.data:
            d = res.data
            return {
                "chat_id":        chat_id,
                "messages":       json.loads(d.get("messages", "[]")),
                "state":          d.get("state", "idle"),
                "last_query":     d.get("last_query"),
                "last_query_info": json.loads(d.get("last_query_info") or "{}"),
            }
    except Exception as e:
        logger.error(f"get_conversation: {e}")
    return {"chat_id": chat_id, "messages": [], "state": "idle",
            "last_query": None, "last_query_info": {}}

async def save_conversation(conv: dict):
    sb = _client()
    try:
        sb.table("conversations").upsert({
            "chat_id":         conv["chat_id"],
            "messages":        json.dumps(conv.get("messages", []), default=str, ensure_ascii=False),
            "state":           conv.get("state", "idle"),
            "last_query":      conv.get("last_query"),
            "last_query_info": json.dumps(conv.get("last_query_info", {}), ensure_ascii=False),
            "updated_at":      datetime.utcnow().isoformat(),
        }, on_conflict="chat_id").execute()
    except Exception as e:
        logger.error(f"save_conversation: {e}")

async def log_search(chat_id: str, query: str, source: str, result_count: int):
    sb = _client()
    try:
        sb.table("search_logs").insert({
            "chat_id": chat_id, "query": query,
            "source": source, "result_count": result_count,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"log_search: {e}")

async def get_stats() -> dict:
    sb = _client()
    try:
        prods = sb.table("products").select("stock_quantity,price_public,is_active", count="exact").execute()
        total = prods.count or 0
        out_of_stock = sum(1 for p in (prods.data or []) if (p.get("stock_quantity") or 0) == 0)
        inventory_value = sum(
            (p.get("stock_quantity") or 0) * (p.get("price_public") or 0)
            for p in (prods.data or [])
        )
        brands_res = sb.table("brands").select("name,id").execute()
        brand_counts = {}
        for b in (brands_res.data or []):
            cnt = sb.table("products").select("id", count="exact").eq("brand_id", b["id"]).execute()
            brand_counts[b["name"]] = cnt.count or 0

        convs = sb.table("conversations").select("id", count="exact").execute()
        searches = sb.table("search_logs").select("result_count").execute()
        total_s = len(searches.data or [])
        resolved = sum(1 for s in (searches.data or []) if (s.get("result_count") or 0) > 0)

        return {
            "total_products": total,
            "out_of_stock": out_of_stock,
            "inventory_value": round(inventory_value, 2),
            "brands": brand_counts,
            "total_conversations": convs.count or 0,
            "total_searches": total_s,
            "resolution_rate": round(resolved / total_s * 100) if total_s else 0,
        }
    except Exception as e:
        logger.error(f"get_stats: {e}")
        return {}
