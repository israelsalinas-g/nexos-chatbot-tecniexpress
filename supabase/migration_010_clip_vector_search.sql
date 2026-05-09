-- ================================================================
-- Migration 010: CLIP vector search con pgvector
-- ================================================================

-- 1. Habilitar pgvector (verificar primero en Supabase Dashboard → Extensions)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Convertir columna embedding a vector(512)
ALTER TABLE public.product_image_embeddings
  ALTER COLUMN embedding TYPE vector(512);

-- 3. Añadir UNIQUE constraint solo si no existe
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_product_image_embeddings_image_id'
  ) THEN
    ALTER TABLE public.product_image_embeddings
      ADD CONSTRAINT uq_product_image_embeddings_image_id
      UNIQUE (product_image_id);
  END IF;
END $$;

-- 4. Índice HNSW para búsqueda coseno rápida
CREATE INDEX IF NOT EXISTS idx_pie_hnsw
  ON public.product_image_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 5. RPC: retorna top-N productos más similares visualmente
CREATE OR REPLACE FUNCTION public.search_by_image_vector(
  query_embedding vector(512),
  p_limit         integer DEFAULT 3
)
RETURNS TABLE (
  product_id        uuid,
  product_image_id  uuid,
  image_url         text,
  similarity        float4,
  sku               text,
  part_number       text,
  name_es           text,
  description_es    text,
  price_public      integer,
  price_technician  integer,
  price_wholesale   integer,
  total_quantity    bigint,
  brand_name        text,
  compatible_models text[]
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT
    pie.product_id,
    pie.product_image_id,
    pie.image_url,
    (1 - (pie.embedding <=> query_embedding))::float4  AS similarity,
    p.sku, p.part_number, p.name_es, p.description_es,
    p.price_public, p.price_technician, p.price_wholesale,
    COALESCE(
      (SELECT SUM(i.quantity) FROM inventory i WHERE i.product_id = p.id),
      p.stock_quantity::bigint
    ) AS total_quantity,
    b.name AS brand_name,
    p.compatible_models
  FROM product_image_embeddings pie
  JOIN products p    ON p.id = pie.product_id
  LEFT JOIN brands b ON b.id = p.brand_id
  WHERE p.is_active = true
  ORDER BY pie.embedding <=> query_embedding
  LIMIT p_limit;
$$;

GRANT EXECUTE ON FUNCTION public.search_by_image_vector TO service_role;
