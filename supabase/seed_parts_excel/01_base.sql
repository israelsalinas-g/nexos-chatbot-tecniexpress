-- Base Data
-- Seed optimizado con Batch Inserts

INSERT INTO public.brands (name, slug) SELECT 'Otras', 'otras' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE slug = 'otras');
INSERT INTO public.brands (name, slug) SELECT 'GE - General Electric', 'ge-general-electric' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE 'GE - General Electric');
INSERT INTO public.brands (name, slug) SELECT 'Mabe', 'mabe' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE 'Mabe');
INSERT INTO public.brands (name, slug) SELECT 'Whirpool', 'whirpool' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE 'Whirpool');
INSERT INTO public.brands (name, slug) SELECT 'Electrolux - Frigidaire', 'electrolux-frigidaire' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE 'Electrolux - Frigidaire');
INSERT INTO public.brands (name, slug) SELECT 'Genérico', 'genérico' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE 'Genérico');
INSERT INTO public.brands (name, slug) SELECT 'LG', 'lg' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE 'LG');
INSERT INTO public.brands (name, slug) SELECT 'Samsung', 'samsung' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE 'Samsung');
INSERT INTO public.categories (name_es, name_en, slug) SELECT 'Otros', 'Otros', 'otros' WHERE NOT EXISTS (SELECT 1 FROM public.categories WHERE slug = 'otros');
INSERT INTO public.warehouses (name) SELECT 'Repuestos Carro 🚐' WHERE NOT EXISTS (SELECT 1 FROM public.warehouses WHERE name ILIKE 'Repuestos Carro 🚐');
INSERT INTO public.warehouses (name) SELECT 'Repuestos Tecni Express / Principal ⚒️🏠' WHERE NOT EXISTS (SELECT 1 FROM public.warehouses WHERE name ILIKE 'Repuestos Tecni Express / Principal ⚒️🏠');
INSERT INTO public.warehouses (name) SELECT 'Repuestos Tienda 2 / SPS Altos V 🏡' WHERE NOT EXISTS (SELECT 1 FROM public.warehouses WHERE name ILIKE 'Repuestos Tienda 2 / SPS Altos V 🏡');
INSERT INTO public.warehouses (name) SELECT 'Tienda Altos Valencia II / SPS' WHERE NOT EXISTS (SELECT 1 FROM public.warehouses WHERE name ILIKE 'Tienda Altos Valencia II / SPS');