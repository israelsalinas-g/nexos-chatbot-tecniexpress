-- ============================================================
-- Migration: Fix Manual Search RPC
-- Mejora la robustez de la búsqueda en manuales técnicos.
-- ============================================================

-- 1. Asegurar índice 'simple' para códigos de parte (sin stemming)
CREATE INDEX IF NOT EXISTS manual_index_fts_simple_idx
  ON public.manual_index
  USING gin(to_tsvector('simple', text_content));

-- 2. Actualizar RPC search_manual_index
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
    -- Combinamos rank de FTS con un boost si el texto contiene el query exacto (para códigos)
    (
      ts_rank(to_tsvector('simple', text_content), websearch_to_tsquery('simple', p_query)) +
      ts_rank(to_tsvector('spanish', text_content), websearch_to_tsquery('spanish', p_query)) +
      (CASE WHEN text_content ILIKE '%' || p_query || '%' THEN 0.5 ELSE 0 END)
    ) AS rank
  FROM manual_index
  WHERE
    (
      -- Intenta match con diccionario simple (mejor para códigos técnicos)
      to_tsvector('simple', text_content) @@ websearch_to_tsquery('simple', p_query)
      OR
      -- Intenta match con diccionario español
      to_tsvector('spanish', text_content) @@ websearch_to_tsquery('spanish', p_query)
      OR
      -- Fallback literal por si los stop words eliminan términos clave
      text_content ILIKE '%' || p_query || '%'
    )
    -- Los filtros son ahora "inclusivos" con NULLs para evitar bloqueos si la metadata falló al indexar
    AND (p_brand IS NULL OR brand IS NULL OR brand ILIKE '%' || p_brand || '%')
    AND (p_model IS NULL OR model_prefix IS NULL OR model_prefix ILIKE '%' || p_model || '%' OR p_model ILIKE '%' || model_prefix || '%')
  ORDER BY rank DESC
  LIMIT 3;
$$;

GRANT EXECUTE ON FUNCTION public.search_manual_index TO service_role;
