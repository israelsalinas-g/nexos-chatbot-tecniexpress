-- ================================================================
-- Migration 006: Refactor categories and add product location
-- ================================================================

-- 1. Add location column to products (if not already there)
ALTER TABLE public.products ADD COLUMN IF NOT EXISTS location text;

-- 2. Move data from categories.name_es to products.location
UPDATE public.products p
SET location = c.name_es
FROM public.categories c
WHERE p.category_id = c.id;

-- 3. Detach categories from products to allow deletion
UPDATE public.products SET category_id = NULL;

-- 4. Delete all existing categories
DELETE FROM public.categories;

-- 5. Create the "Otros" category
INSERT INTO public.categories (name_es, name_en, slug)
SELECT 'Otros', 'Otros', 'otros'
WHERE NOT EXISTS (SELECT 1 FROM public.categories WHERE slug = 'otros');

-- 6. Assign "Otros" category to all existing products
UPDATE public.products
SET category_id = (SELECT id FROM public.categories WHERE slug = 'otros' LIMIT 1);

-- 7. Update fts trigger to include location
CREATE OR REPLACE FUNCTION public.products_update_fts() RETURNS trigger AS $$
BEGIN
  NEW.fts := 
    to_tsvector('spanish',
      coalesce(NEW.name_es, '')            || ' ' ||
      coalesce(NEW.name_en, '')            || ' ' ||
      coalesce(NEW.description_es, '')     || ' ' ||
      coalesce(NEW.sku, '')                || ' ' ||
      coalesce(NEW.part_number, '')        || ' ' ||
      coalesce(NEW.location, '')           || ' ' ||
      coalesce(array_to_string(NEW.tags, ' '), '') || ' ' ||
      coalesce(array_to_string(NEW.compatible_models, ' '), '')
    );
  RETURN NEW;
END
$$ LANGUAGE plpgsql;

-- 8. Re-crear la vista products_full para incluir location
CREATE OR REPLACE VIEW public.products_full AS
SELECT
  p.id, p.sku, p.part_number, p.slug, p.name_es, p.name_en,
  p.description_es, p.description_en, p.compatible_models, p.tags,
  p.price_public, p.price_technician, p.price_wholesale,
  p.stock_quantity, p.stock_min, p.track_inventory,
  p.is_active, p.is_featured, p.fts,
  b.name AS brand_name, b.slug AS brand_slug,
  c.name_es AS category_name,
  p.location
FROM public.products p
LEFT JOIN public.brands b ON b.id = p.brand_id
LEFT JOIN public.categories c ON c.id = p.category_id
WHERE p.is_active = true;
