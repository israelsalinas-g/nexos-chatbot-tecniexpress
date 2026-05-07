-- ================================================================
-- RepuestosBot — Fix búsqueda en Supabase
-- Ejecutar en: Supabase Dashboard > SQL Editor
-- ================================================================

-- 1. Agregar columna FTS al esquema real (name_es, description_es, tags, sku, part_number)
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('spanish',
      coalesce(name_es, '')        || ' ' ||
      coalesce(name_en, '')        || ' ' ||
      coalesce(description_es, '') || ' ' ||
      coalesce(sku, '')            || ' ' ||
      coalesce(part_number, '')    || ' ' ||
      coalesce(array_to_string(tags, ' '), '') || ' ' ||
      coalesce(array_to_string(compatible_models, ' '), '')
    )
  ) STORED;

CREATE INDEX IF NOT EXISTS idx_products_fts ON products USING GIN (fts);

-- Índices extra para filtros frecuentes
CREATE INDEX IF NOT EXISTS idx_products_brand_id  ON products (brand_id);
CREATE INDEX IF NOT EXISTS idx_products_sku        ON products (sku);
CREATE INDEX IF NOT EXISTS idx_products_part       ON products (part_number);
CREATE INDEX IF NOT EXISTS idx_products_active     ON products (is_active) WHERE is_active = true;

-- 2. Vista que une products + brands + categories (evita JOINs manuales en Python)
--    Ajusta los nombres de tabla si son distintos en tu BD
CREATE OR REPLACE VIEW products_full AS
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
FROM products p
LEFT JOIN brands    b ON b.id = p.brand_id
LEFT JOIN categories c ON c.id = p.category_id
WHERE p.is_active = true;

-- 3. Función de búsqueda combinada (opcional, para llamar con rpc())
--    Busca por texto Y filtra por marca en una sola llamada
CREATE OR REPLACE FUNCTION search_products(
  query_text  text DEFAULT NULL,
  brand_name  text DEFAULT NULL,
  model_text  text DEFAULT NULL,
  max_results int  DEFAULT 10
)
RETURNS SETOF products_full
LANGUAGE sql STABLE
AS $$
  SELECT *
  FROM   products_full
  WHERE
    -- Filtro de texto libre
    (query_text IS NULL OR fts @@ plainto_tsquery('spanish', query_text))
    -- Filtro de marca (insensible a mayúsculas)
    AND (brand_name IS NULL OR brand_name ILIKE '%' || brand_name || '%')
    -- Filtro de modelo compatible
    AND (model_text IS NULL OR compatible_models @> ARRAY[upper(model_text)])
  ORDER BY
    CASE WHEN query_text IS NOT NULL
         THEN ts_rank(fts, plainto_tsquery('spanish', query_text))
         ELSE 0 END DESC,
    is_featured DESC,
    stock_quantity DESC
  LIMIT max_results;
$$;
