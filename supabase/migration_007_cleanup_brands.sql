-- ================================================================
-- Migration 007: Cleanup invalid brands
-- ================================================================

-- 1. Create the "Otras" brand if it doesn't exist
INSERT INTO public.brands (name, slug)
SELECT 'Otras', 'otras'
WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE slug = 'otras');

-- 2. Reassign products with invalid brands to the "Otras" brand
UPDATE public.products
SET brand_id = (SELECT id FROM public.brands WHERE slug = 'otras' LIMIT 1)
WHERE brand_id IN (
    SELECT id FROM public.brands
    WHERE slug IN ('apply-parts', 'precio-actualizado', 'sin-isv', 'actuador')
);

-- 3. Delete the invalid brands
DELETE FROM public.brands
WHERE slug IN ('apply-parts', 'precio-actualizado', 'sin-isv', 'actuador');
