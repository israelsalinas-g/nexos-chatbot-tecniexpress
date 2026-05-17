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


def is_new_user(chat_id: int) -> bool:
    """True si el chat nunca ha interactuado con el bot (sin registro en telegram_sessions)."""
    result = (
        _supabase.table("telegram_sessions")
        .select("chat_id")
        .eq("chat_id", chat_id)
        .maybe_single()
        .execute()
    )
    return result.data is None


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
    Búsqueda en 4 etapas (más flexible):
    1. Búsqueda por palabras individuales (split del query)
    2. Combinación marca + tipo de producto
    3. FTS por texto completo
    4. ILIKE como fallback final

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

    # Consolidar todos los términos de búsqueda
    all_terms = list(set(filter(None, [part] + search_terms)))
    all_terms_str = " ".join(all_terms)

    # Resolver marca una sola vez para reutilizar en todas las etapas
    brand_id = None
    brand_name_resolved = brand
    if brand:
        try:
            brand_res = _supabase.table("brands").select("id, name").ilike(
                "name", f"%{brand}%"
            ).limit(1).execute()
            if brand_res.data:
                brand_id = brand_res.data[0]["id"]
                brand_name_resolved = brand_res.data[0]["name"]
        except Exception as e:
            print(f"[supabase] Error resolviendo marca '{brand}': {e}")

    # ============================================================
    # ETAPA 1: Intersección de palabras (AND entre todas)
    # El producto debe contener TODAS las palabras del query
    # ============================================================
    individual_words = [w.strip() for w in all_terms_str.split() if len(w.strip()) >= 3]

    if individual_words:
        word_id_sets: list[set] = []
        for word in individual_words[:5]:
            try:
                or_conditions = [
                    f"name_es.ilike.%{word}%",
                    f"sku.ilike.%{word}%",
                    f"part_number.ilike.%{word}%",
                    f"description_es.ilike.%{word}%",
                ]
                q = (
                    _supabase.table("products")
                    .select("id")
                    .eq("is_active", True)
                    .or_(",".join(or_conditions))
                )
                if brand_id:
                    q = q.eq("brand_id", brand_id)
                r = q.execute()
                word_id_sets.append({row["id"] for row in r.data} if r.data else set())
            except Exception as e:
                print(f"[supabase] Error word search '{word}': {e}")
                word_id_sets.append(set())

        # Intersectar: solo IDs presentes en TODAS las palabras buscadas
        matching_ids: set = word_id_sets[0]
        for s in word_id_sets[1:]:
            matching_ids &= s

        if matching_ids:
            try:
                r = (
                    _supabase.table("products")
                    .select(
                        "id, sku, part_number, name_es, description_es, location, "
                        "price_public, price_technician, price_wholesale, stock_quantity, brand_id, "
                        "compatible_models, tags, slug"
                    )
                    .eq("is_active", True)
                    .in_("id", list(matching_ids))
                    .limit(10)
                    .execute()
                )
                if r.data:
                    sources.append("word_match")
                    for prod in r.data:
                        if brand_name_resolved:
                            prod["brand_name"] = brand_name_resolved
                        img_row = (
                            _supabase.table("product_images")
                            .select("url")
                            .eq("product_id", prod["id"])
                            .eq("is_primary", True)
                            .maybe_single()
                            .execute()
                        )
                        if img_row.data:
                            prod["image_url"] = img_row.data["url"]
                        results_by_id[prod["id"]] = prod
            except Exception as e:
                print(f"[supabase] Error fetching intersected products: {e}")

    # ============================================================
    # NUEVA ETAPA 1.5: Búsqueda SOLO por marca
    # Si el usuario solo escribe "LG" o "Samsung", mostrar productos de esa marca
    # ============================================================
    if brand and not part and not model and not code:
        possible_brands = ["LG", "Samsung", "Mabe", "GE", "Whirlpool", "Frigidaire"]
        brand_normalized = brand.strip().upper()
        
        # Verificar si lo que escribió es una marca válida
        matched_brand = None
        for b in possible_brands:
            if b.lower() in brand_normalized.lower() or brand_normalized.lower() in b.lower():
                matched_brand = b
                break
        
        if matched_brand and brand_id:
            try:
                q = (
                    _supabase.table("products")
                    .select(
                        "id, sku, part_number, name_es, description_es, location, "
                        "price_public, price_technician, price_wholesale, stock_quantity, brand_id, "
                        "compatible_models, tags, slug"
                    )
                    .eq("brand_id", brand_id)
                    .eq("is_active", True)
                    .limit(10)
                    .execute()
                )
                if q.data:
                    sources.append("brand_only")
                    for prod in q.data:
                        prod["brand_name"] = brand_name_resolved
                        img_row = (
                            _supabase.table("product_images")
                            .select("url")
                            .eq("product_id", prod["id"])
                            .eq("is_primary", True)
                            .maybe_single()
                            .execute()
                        )
                        if img_row.data:
                            prod["image_url"] = img_row.data["url"]
                        results_by_id[prod["id"]] = prod
            except Exception as e:
                print(f"[supabase] Error brand-only search: {e}")

    # ============================================================
    # NUEVA ETAPA 2: Búsqueda combinada marca + tipo de producto
    # Ejemplo: "actuador Whirlpool" o "Banda LG"
    # ============================================================
    if brand and part and brand_id:
        try:
            q = (
                _supabase.table("products")
                .select(
                    "id, sku, part_number, name_es, description_es, location, "
                    "price_public, price_technician, price_wholesale, stock_quantity, brand_id, "
                    "compatible_models, tags, slug"
                )
                .eq("is_active", True)
                .or_(f"name_es.ilike.%{part}%,description_es.ilike.%{part}%")
                .eq("brand_id", brand_id)
                .limit(10)
            )
            r = q.execute()
            if r.data:
                sources.append("brand_product")
                for prod in r.data:
                    prod["brand_name"] = brand_name_resolved
                    img_row = (
                        _supabase.table("product_images")
                        .select("url")
                        .eq("product_id", prod["id"])
                        .eq("is_primary", True)
                        .maybe_single()
                        .execute()
                    )
                    if img_row.data:
                        prod["image_url"] = img_row.data["url"]
                    if prod["id"] not in results_by_id:
                        results_by_id[prod["id"]] = prod
                    else:
                        results_by_id[prod["id"]]["_double_match"] = True
        except Exception as e:
            print(f"[supabase] Error brand+product search: {e}")

    # ============================================================
    # ETAPA 3: FTS por texto (solo si hay query y no hay muchos resultados)
    # ============================================================
    if all_terms_str.strip() and len(results_by_id) < 3:
        fts_query = part.strip() if part else all_terms_str.strip()
        try:
            r = _supabase.rpc("search_products_v2", {
                "p_query": fts_query,
                "p_brand_name": brand,
                "p_model": model,
                "p_limit": 8,
            }).execute()
            if r.data:
                sources.append("fts")
                for product in r.data:
                    pid = product["id"]
                    if pid not in results_by_id:
                        results_by_id[pid] = product
                    else:
                        results_by_id[pid]["_double_match"] = True
        except Exception as e:
            print(f"[supabase] Error FTS v2: {e}")

    # ============================================================
    # ETAPA 4: Compatibilidad por modelo (si hay modelo)
    # ============================================================
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

    # ============================================================
    # ETAPA 5: ILIKE fallback general (último recurso)
    # ============================================================
    if not results_by_id and all_terms_str.strip():
        try:
            words = [w for w in all_terms_str.split() if len(w) > 2][:5]
            fallback_id_sets: list[set] = []
            for w in words:
                or_conditions = [
                    f"name_es.ilike.%{w}%",
                    f"sku.ilike.%{w}%",
                    f"part_number.ilike.%{w}%",
                    f"description_es.ilike.%{w}%",
                ]
                q = (
                    _supabase.table("products")
                    .select("id")
                    .eq("is_active", True)
                    .or_(",".join(or_conditions))
                )
                if brand_id:
                    q = q.eq("brand_id", brand_id)
                r = q.execute()
                fallback_id_sets.append({row["id"] for row in r.data} if r.data else set())

            if fallback_id_sets:
                fallback_ids: set = fallback_id_sets[0]
                for s in fallback_id_sets[1:]:
                    fallback_ids &= s

                if fallback_ids:
                    r_ilike = (
                        _supabase.table("products")
                        .select(
                            "id, sku, part_number, name_es, description_es, location, "
                            "price_public, price_technician, price_wholesale, stock_quantity, brand_id, "
                            "compatible_models, tags, slug"
                        )
                        .eq("is_active", True)
                        .in_("id", list(fallback_ids))
                        .limit(10)
                        .execute()
                    )
                    if r_ilike.data:
                        sources.append("ilike")
                        for product in r_ilike.data:
                            if brand_name_resolved:
                                product["brand_name"] = brand_name_resolved
                            results_by_id[product["id"]] = product
        except Exception as e:
            print(f"[supabase] Error ILIKE fallback: {e}")

    # Ordenar resultados: primero los que tienen doble match
    sorted_results = sorted(
        results_by_id.values(),
        key=lambda p: (p.get("_double_match", False), p.get("rank", 0)),
        reverse=True,
    )

    top = _enrich_products(sorted_results[:5])
    return top, list(set(sources))


def _enrich_products(products: list[dict]) -> list[dict]:
    """
    Completa slug y price_public para todos los productos.
    Necesario porque los RPCs de Postgres no devuelven esos campos.
    """
    all_ids = [p["id"] for p in products if p.get("id")]
    if not all_ids:
        return products

    try:
        r = _supabase.table("products").select(
            "id, slug, price_public"
        ).in_("id", all_ids).execute()
        data_map = {row["id"]: row for row in (r.data or [])}
        for product in products:
            extra = data_map.get(product["id"], {})
            if extra.get("slug"):
                product["slug"] = extra["slug"]
            if extra.get("price_public"):
                product["price_public"] = extra["price_public"]
        print(f"[enrich] {len(products)} productos — slugs: {[p.get('slug') for p in products]}")
    except Exception as e:
        print(f"[supabase] Error enriqueciendo productos: {e}")

    return products


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



def get_products_with_images(brand: str | None = None, limit: int = 20) -> list[dict]:
    """
    Devuelve productos que tienen imagen en el bucket.
    Se usa como pool para búsqueda visual cuando el texto no encuentra nada.
    Opcionalmente filtra por marca para reducir el espacio de comparación.
    """
    try:
        # Primero obtener IDs de productos con imagen
        img_q = _supabase.table("product_images").select("product_id, url").eq("is_primary", True)
        img_r = img_q.execute()
        
        if not img_r.data:
            return []
        
        product_ids_with_images = [row["product_id"] for row in img_r.data]
        image_urls = {row["product_id"]: row["url"] for row in img_r.data}
        
        # Ahora obtener los productos
        q = _supabase.table("products").select(
            "id, sku, part_number, name_es, description_es, location, "
            "price_public, price_technician, price_wholesale, stock_quantity, brand_id, "
            "compatible_models, tags, slug"
        ).eq("is_active", True).in_("id", product_ids_with_images)
        
        if brand:
            brand_res = _supabase.table("brands").select("id").ilike(
                "name", f"%{brand}%"
            ).limit(1).execute()
            if brand_res.data:
                q = q.eq("brand_id", brand_res.data[0]["id"])

        r = q.limit(limit).execute()
        
        # Agregar image_url a cada producto
        results = r.data or []
        for prod in results:
            prod["image_url"] = image_urls.get(prod["id"])
        
        return results
    except Exception as e:
        print(f"[supabase] Error get_products_with_images: {e}")
        return []


def search_by_image_embedding(embedding: list[float], limit: int = 3) -> list[dict]:
    """
    Búsqueda por similitud visual usando el embedding CLIP de la imagen del usuario.
    Llama al RPC search_by_image_vector y normaliza el resultado al mismo shape
    que usan los demás métodos de búsqueda.
    Retorna lista vacía si pgvector no está activo o la tabla está sin datos.
    """
    try:
        r = _supabase.rpc(
            "search_by_image_vector",
            {"query_embedding": embedding, "p_limit": limit},
        ).execute()
        rows = r.data or []
        for row in rows:
            row["id"] = row.pop("product_id")
            row["_clip_similarity"] = row.pop("similarity", 0.0)
            row["_is_visual_match"] = True
        return rows
    except Exception as e:
        print(f"[supabase] Error search_by_image_embedding: {e}")
        return []


# Etiquetas legibles para cada fuente de búsqueda
SOURCE_LABELS: dict[str, str] = {
    "code":         "🗄️ BD · código exacto",
    "word_match":   "🗄️ BD · palabras relacionadas",
    "brand_only":   "🗄️ BD · productos de marca",
    "brand_product": "🗄️ BD · marca + producto",
    "fts":          "🗄️ BD · búsqueda por texto",
    "ilike":        "🗄️ BD · búsqueda aproximada",
    "model":        "🗄️ BD · compatibilidad de modelo",
    "visual":       "👁️ Comparación visual con catálogo",
    "clip":         "🖼️ Búsqueda visual CLIP",
    "manual":       "📄 Manuales técnicos PDF",
    "gdrive":       "📄 Manuales PDF (Drive)",
    "web":          "🌐 Web fabricante",
}
