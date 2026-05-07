-- ============================================================
-- Migration: Telegram Chatbot Tables & Stored Procedures
-- NOTA: Este archivo es una copia de referencia.
-- La migración oficial está en el proyecto nexos-tecni-express:
--   supabase/migrations/0005_telegram_bot.sql
-- ============================================================

-- ─────────────────────────────────────────────────────────────
-- 1. telegram_sessions — conversación stateful por chat
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.telegram_sessions (
  chat_id    bigint PRIMARY KEY,
  state      text NOT NULL DEFAULT 'idle'
             CHECK (state IN ('idle', 'awaiting_brand', 'awaiting_model', 'awaiting_part')),
  context    jsonb NOT NULL DEFAULT '{}',
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- El bot usa service_role key que bypasea RLS, pero igual lo habilitamos
ALTER TABLE public.telegram_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "telegram_sessions_service_only"
  ON public.telegram_sessions FOR ALL USING (false);

CREATE TRIGGER set_telegram_sessions_updated_at
  BEFORE UPDATE ON public.telegram_sessions
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();


-- ─────────────────────────────────────────────────────────────
-- 2. manual_index — PDFs de manuales indexados desde Google Drive
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.manual_index (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_name   text NOT NULL,
  brand           text,
  model_prefix    text,
  text_content    text NOT NULL,
  chunk_index     integer NOT NULL DEFAULT 0,
  source_drive_id text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_drive_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS manual_index_fts_idx
  ON public.manual_index
  USING gin(to_tsvector('spanish', text_content));

CREATE INDEX IF NOT EXISTS manual_index_brand_idx ON public.manual_index(brand);
CREATE INDEX IF NOT EXISTS manual_index_model_idx ON public.manual_index(model_prefix);

ALTER TABLE public.manual_index ENABLE ROW LEVEL SECURITY;
CREATE POLICY "manual_index_service_only"
  ON public.manual_index FOR ALL USING (false);

CREATE TRIGGER set_manual_index_updated_at
  BEFORE UPDATE ON public.manual_index
  FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();


-- ─────────────────────────────────────────────────────────────
-- 3. Índice FTS adicional en description_es de products
--    (el existente solo cubre name_es + part_number + sku)
-- ─────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS products_desc_fts_idx
  ON public.products
  USING gin(to_tsvector('spanish', coalesce(description_es, '')));


-- ─────────────────────────────────────────────────────────────
-- 4. RPC: search_products_fts
--    Búsqueda por nombre, SKU y número de parte usando FTS
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.search_products_fts(
  p_query      text,
  p_brand_name text DEFAULT NULL,
  p_limit      integer DEFAULT 5
)
RETURNS TABLE (
  id              uuid,
  sku             text,
  part_number     text,
  name_es         text,
  description_es  text,
  price_public    integer,
  price_technician integer,
  price_wholesale integer,
  total_quantity  bigint,
  brand_name      text,
  image_url       text,
  compatible_models text[],
  rank            float4
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    p.id,
    p.sku,
    p.part_number,
    p.name_es,
    p.description_es,
    p.price_public,
    p.price_technician,
    p.price_wholesale,
    COALESCE(
      (SELECT SUM(i.quantity) FROM inventory i WHERE i.product_id = p.id),
      p.stock_quantity::bigint
    ) AS total_quantity,
    b.name AS brand_name,
    (
      SELECT pi.url FROM product_images pi
      WHERE pi.product_id = p.id AND pi.is_primary = true
      LIMIT 1
    ) AS image_url,
    p.compatible_models,
    ts_rank(
      to_tsvector('spanish',
        p.name_es || ' ' ||
        COALESCE(p.part_number, '') || ' ' ||
        p.sku || ' ' ||
        COALESCE(p.description_es, '')
      ),
      websearch_to_tsquery('spanish', p_query)
    ) AS rank
  FROM products p
  LEFT JOIN brands b ON p.brand_id = b.id
  WHERE
    p.is_active = true
    AND to_tsvector('spanish',
      p.name_es || ' ' ||
      COALESCE(p.part_number, '') || ' ' ||
      p.sku || ' ' ||
      COALESCE(p.description_es, '')
    ) @@ websearch_to_tsquery('spanish', p_query)
    AND (p_brand_name IS NULL OR b.name ILIKE '%' || p_brand_name || '%')
  ORDER BY rank DESC
  LIMIT p_limit;
$$;

GRANT EXECUTE ON FUNCTION public.search_products_fts TO service_role;


-- ─────────────────────────────────────────────────────────────
-- 5. RPC: search_products_by_model
--    Búsqueda por compatibilidad de modelo de equipo
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.search_products_by_model(
  p_model       text,
  p_brand       text DEFAULT NULL,
  p_part_filter text DEFAULT NULL,
  p_limit       integer DEFAULT 10
)
RETURNS TABLE (
  id              uuid,
  sku             text,
  part_number     text,
  name_es         text,
  description_es  text,
  price_public    integer,
  price_technician integer,
  price_wholesale integer,
  total_quantity  bigint,
  brand_name      text,
  image_url       text,
  match_type      text
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT DISTINCT ON (p.id)
    p.id,
    p.sku,
    p.part_number,
    p.name_es,
    p.description_es,
    p.price_public,
    p.price_technician,
    p.price_wholesale,
    COALESCE(
      (SELECT SUM(i.quantity) FROM inventory i WHERE i.product_id = p.id),
      p.stock_quantity::bigint
    ) AS total_quantity,
    b.name AS brand_name,
    (
      SELECT pi.url FROM product_images pi
      WHERE pi.product_id = p.id AND pi.is_primary = true
      LIMIT 1
    ) AS image_url,
    CASE
      WHEN EXISTS (
        SELECT 1 FROM product_compatibility pc
        JOIN appliance_models am ON am.id = pc.appliance_model_id
        WHERE pc.product_id = p.id
          AND am.model_number ILIKE '%' || p_model || '%'
      ) THEN 'relational'
      ELSE 'array'
    END AS match_type
  FROM products p
  LEFT JOIN brands b ON p.brand_id = b.id
  WHERE
    p.is_active = true
    AND (
      -- Tabla relacional product_compatibility + appliance_models
      EXISTS (
        SELECT 1 FROM product_compatibility pc
        JOIN appliance_models am ON am.id = pc.appliance_model_id
        WHERE pc.product_id = p.id
          AND am.model_number ILIKE '%' || p_model || '%'
          AND (p_brand IS NULL OR b.name ILIKE '%' || p_brand || '%')
      )
      OR
      -- Fallback: array compatible_models[] en products
      EXISTS (
        SELECT 1 FROM unnest(p.compatible_models) AS cm
        WHERE cm ILIKE '%' || p_model || '%'
      )
    )
    AND (
      p_part_filter IS NULL
      OR to_tsvector('spanish', p.name_es)
         @@ websearch_to_tsquery('spanish', p_part_filter)
    )
  ORDER BY p.id, p.name_es
  LIMIT p_limit;
$$;

GRANT EXECUTE ON FUNCTION public.search_products_by_model TO service_role;


-- ─────────────────────────────────────────────────────────────
-- 6. RPC: search_manual_index
--    Búsqueda FTS en los manuales PDF indexados
-- ─────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION public.search_manual_index(
  p_query text,
  p_brand text DEFAULT NULL,
  p_model text DEFAULT NULL
)
RETURNS TABLE (
  id            uuid,
  document_name text,
  brand         text,
  model_prefix  text,
  excerpt       text,
  rank          float4
)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT
    id,
    document_name,
    brand,
    model_prefix,
    substring(text_content from 1 for 600) AS excerpt,
    ts_rank(
      to_tsvector('spanish', text_content),
      websearch_to_tsquery('spanish', p_query)
    ) AS rank
  FROM manual_index
  WHERE
    to_tsvector('spanish', text_content) @@ websearch_to_tsquery('spanish', p_query)
    AND (p_brand IS NULL OR brand ILIKE '%' || p_brand || '%')
    AND (p_model IS NULL OR model_prefix ILIKE '%' || p_model || '%')
  ORDER BY rank DESC
  LIMIT 3;
$$;

GRANT EXECUTE ON FUNCTION public.search_manual_index TO service_role;
