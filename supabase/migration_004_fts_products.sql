-- ================================================================
-- Migration 004: FTS mejorado en products + vista products_full
-- Ejecutar en: Supabase Dashboard > SQL Editor
-- ================================================================

-- 1. Columna FTS generada sobre todos los campos buscables
--    Permite búsquedas más rápidas que calcular tsvector en cada consulta.
ALTER TABLE public.products
  ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('spanish',
      coalesce(name_es, '')            || ' ' ||
      coalesce(name_en, '')            || ' ' ||
      coalesce(description_es, '')     || ' ' ||
      coalesce(sku, '')                || ' ' ||
      coalesce(part_number, '')        || ' ' ||
      coalesce(array_to_string(tags, ' '), '') || ' ' ||
      coalesce(array_to_string(compatible_models, ' '), '')
    )
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_products_fts    ON public.products USING GIN (fts);
CREATE INDEX IF NOT EXISTS idx_products_brand  ON public.products (brand_id);
CREATE INDEX IF NOT EXISTS idx_products_sku    ON public.products (sku);
CREATE INDEX IF NOT EXISTS idx_products_part   ON public.products (part_number);
CREATE INDEX IF NOT EXISTS idx_products_active ON public.products (is_active) WHERE is_active = true;


-- 2. Vista products_full (JOIN con brands y categories)
--    Evita JOINs manuales en Python y simplifica los RPCs.
CREATE OR REPLACE VIEW public.products_full AS
SELECT
  p.id,
  p.sku,
  p.part_number,
  p.slug,
  p.name_es,
  p.name_en,
  p.description_es,
  p.description_en,
  p.compatible_models,
  p.tags,
  p.price_public,
  p.price_technician,
  p.price_wholesale,
  p.stock_quantity,
  p.stock_min,
  p.track_inventory,
  p.is_active,
  p.is_featured,
  p.fts,
  b.name   AS brand_name,
  b.slug   AS brand_slug,
  c.name_es AS category_name
FROM public.products p
LEFT JOIN public.brands     b ON b.id = p.brand_id
LEFT JOIN public.categories c ON c.id = p.category_id
WHERE p.is_active = true;


-- 3. RPC: search_products_v2 — usa la columna fts stored para mejor rendimiento
--    Compatible con el código Python en supabase_service.py
CREATE OR REPLACE FUNCTION public.search_products_v2(
  p_query      text DEFAULT NULL,
  p_brand_name text DEFAULT NULL,
  p_model      text DEFAULT NULL,
  p_limit      integer DEFAULT 8
)
RETURNS TABLE (
  id               uuid,
  sku              text,
  part_number      text,
  name_es          text,
  description_es   text,
  price_public     integer,
  price_technician integer,
  price_wholesale  integer,
  total_quantity   bigint,
  brand_name       text,
  image_url        text,
  compatible_models text[],
  rank             float4
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
    CASE
      WHEN p_query IS NOT NULL THEN ts_rank(p.fts, plainto_tsquery('spanish', p_query))
      ELSE 0.0
    END AS rank
  FROM public.products p
  LEFT JOIN public.brands b ON b.id = p.brand_id
  WHERE
    p.is_active = true
    AND (
      p_query IS NULL
      OR p.fts @@ plainto_tsquery('spanish', p_query)
    )
    AND (p_brand_name IS NULL OR b.name ILIKE '%' || p_brand_name || '%')
    AND (
      p_model IS NULL
      OR EXISTS (
        SELECT 1 FROM unnest(p.compatible_models) cm WHERE cm ILIKE '%' || p_model || '%'
      )
      OR EXISTS (
        SELECT 1 FROM product_compatibility pc
        JOIN appliance_models am ON am.id = pc.appliance_model_id
        WHERE pc.product_id = p.id AND am.model_number ILIKE '%' || p_model || '%'
      )
    )
  ORDER BY rank DESC, p.is_featured DESC, p.stock_quantity DESC
  LIMIT p_limit;
$$;

GRANT EXECUTE ON FUNCTION public.search_products_v2 TO service_role;
