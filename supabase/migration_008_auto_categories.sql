-- ================================================================
-- Migration 008: Auto-categorize products by name
-- ================================================================

-- 1. Insert specific categories
INSERT INTO public.categories (name_es, name_en, slug)
SELECT val.name_es, val.name_en, val.slug
FROM (
  VALUES 
  ('Válvulas', 'Válvulas', 'valvulas'),
  ('Bandas', 'Bandas', 'bandas'),
  ('Switches', 'Switches', 'switches'),
  ('Bombas', 'Bombas', 'bombas'),
  ('Tarjetas Electrónicas', 'Tarjetas Electrónicas', 'tarjetas-electronicas'),
  ('Motores', 'Motores', 'motores'),
  ('Sensores', 'Sensores', 'sensores'),
  ('Filtros', 'Filtros', 'filtros'),
  ('Termostatos', 'Termostatos', 'termostatos'),
  ('Resistencias', 'Resistencias', 'resistencias'),
  ('Actuadores', 'Actuadores', 'actuadores'),
  ('Poleas', 'Poleas', 'poleas'),
  ('Capacitores', 'Capacitores', 'capacitores'),
  ('Mangueras', 'Mangueras', 'mangueras'),
  ('Compresores', 'Compresores', 'compresores'),
  ('Amortiguadores', 'Amortiguadores', 'amortiguadores')
) AS val(name_es, name_en, slug)
WHERE NOT EXISTS (SELECT 1 FROM public.categories c WHERE c.slug = val.slug);

-- 2. Update existing products based on their name_es
UPDATE public.products p
SET category_id = c.id
FROM public.categories c
WHERE c.slug = (
  CASE 
    WHEN p.name_es ILIKE '%valvula%' OR p.name_es ILIKE '%válvula%' THEN 'valvulas'
    WHEN p.name_es ILIKE '%banda%' THEN 'bandas'
    WHEN p.name_es ILIKE '%switch%' OR p.name_es ILIKE '%interruptor%' THEN 'switches'
    WHEN p.name_es ILIKE '%bomba%' THEN 'bombas'
    WHEN p.name_es ILIKE '%tarjeta%' THEN 'tarjetas-electronicas'
    WHEN p.name_es ILIKE '%motor%' THEN 'motores'
    WHEN p.name_es ILIKE '%sensor%' THEN 'sensores'
    WHEN p.name_es ILIKE '%filtro%' THEN 'filtros'
    WHEN p.name_es ILIKE '%termostato%' THEN 'termostatos'
    WHEN p.name_es ILIKE '%resistencia%' THEN 'resistencias'
    WHEN p.name_es ILIKE '%actuador%' THEN 'actuadores'
    WHEN p.name_es ILIKE '%polea%' THEN 'poleas'
    WHEN p.name_es ILIKE '%capacitor%' THEN 'capacitores'
    WHEN p.name_es ILIKE '%manguera%' THEN 'mangueras'
    WHEN p.name_es ILIKE '%compresor%' THEN 'compresores'
    WHEN p.name_es ILIKE '%amortiguador%' THEN 'amortiguadores'
    ELSE 'otros'
  END
);
