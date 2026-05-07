-- ============================================================
-- Migration: Advanced Manual Search (v3)
-- Soporta búsqueda por múltiples números de parte y match parcial.
-- ============================================================

CREATE OR REPLACE FUNCTION public.search_manual_index(
  p_query         text,
  p_brand         text DEFAULT NULL,
  p_model         text DEFAULT NULL,
  p_part_numbers  text[] DEFAULT '{}'
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
    (
      -- Rank por query principal (AND/Spanish)
      ts_rank(to_tsvector('spanish', text_content), websearch_to_tsquery('spanish', p_query)) * 2 +
      -- Rank por query principal (OR/Spanish - para cuando no todas las palabras coinciden)
      ts_rank(to_tsvector('spanish', text_content), websearch_to_tsquery('spanish', replace(p_query, ' ', ' | '))) +
      -- Boost masivo si coincide alguno de los números de parte (Simple)
      (
        SELECT COALESCE(SUM(ts_rank(to_tsvector('simple', text_content), to_tsquery('simple', pn))), 0)
        FROM unnest(p_part_numbers) pn
        WHERE to_tsvector('simple', text_content) @@ to_tsquery('simple', pn)
      ) * 10 +
      -- Boost si el modelo está en el texto
      (CASE WHEN p_model IS NOT NULL AND text_content ILIKE '%' || p_model || '%' THEN 1.0 ELSE 0 END)
    ) AS rank
  FROM manual_index
  WHERE
    (
      -- Coincide con el query principal (al menos una palabra significativa)
      to_tsvector('spanish', text_content) @@ websearch_to_tsquery('spanish', replace(p_query, ' ', ' | '))
      OR
      -- O coincide con alguno de los números de parte
      EXISTS (
        SELECT 1 FROM unnest(p_part_numbers) pn
        WHERE text_content ILIKE '%' || pn || '%'
      )
    )
    -- Filtros de marca/modelo siguen siendo opcionales para evitar bloqueos por metadata vacía
    AND (p_brand IS NULL OR brand IS NULL OR brand ILIKE '%' || p_brand || '%')
    AND (p_model IS NULL OR model_prefix IS NULL OR model_prefix ILIKE '%' || p_model || '%' OR p_model ILIKE '%' || model_prefix || '%')
  ORDER BY rank DESC
  LIMIT 3;
$$;
