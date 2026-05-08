-- seed_part2_products.sql
-- Productos (VERSION ULTRA-ROBUSTA POR NOMBRES)

INSERT INTO public.products (id, sku, part_number, slug, name_es, name_en, brand_id, category_id, description_es, price_public, price_technician, price_wholesale)
SELECT 
    t.id::uuid, 
    t.sku, 
    t.part_number, 
    LOWER(REPLACE(t.sku, ' ', '-')), 
    t.name_es, 
    t.name_es,
    (SELECT b.id FROM public.brands b WHERE b.name ILIKE t.brand_name LIMIT 1),
    (SELECT c.id FROM public.categories c WHERE c.name_es ILIKE t.category_name LIMIT 1),
    t.description_es, 
    t.price_public, 
    t.price_technician, 
    t.price_wholesale
FROM (VALUES 
('10965e64-d621-5a55-8968-3069ba339797', 'A1-42296', 'A1-42296', 'Actuador de embrague de lavadora Whirlpool 13 pines', 'Mabe', 'Actuador', 'Actuador de embrague de lavadora Whirlpool 13 pines. (W10006355)', 1150, 850, 750), 
('23e67094-1a93-5471-a0f5-93dfd59a7217', 'A1-42301', 'A1-42301', 'Actuador de embrague de lavadora Whirlpool 6 pines', 'Mabe', 'Actuador', 'Actuador de embrague de lavadora Whirlpool 6 pines. (W10597177)', 1050, 750, 650), 
('5e665979-d5c2-5813-890f-90e6784d169e', 'A1-42330', 'A1-42330', 'Actuador lavadora GE mabe 6 pines', 'Mabe', 'Actuador', 'Actuador lavadora GE mabe 6 pines (WH12X20000)', 1150, 850, 750), 
('87627cb5-a0bc-5975-a83d-045373379659', 'A1-42302', 'A1-42302', 'Actuador de lavadora Whirlpool 6 pines (GENERICO)', 'Mabe', 'Actuador', 'Actuador de lavadora Whirlpool 6 pines (GENERICO) (W10597177)', 750, 550, 480)
) AS t(id, sku, part_number, name_es, brand_name, category_name, description_es, price_public, price_technician, price_wholesale)
WHERE NOT EXISTS (SELECT 1 FROM public.products p WHERE p.id = t.id::uuid OR p.sku = t.sku);
