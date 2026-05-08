-- seed_part4_inventory.sql
-- Inventario (VERSION ULTRA-ROBUSTA POR NOMBRES Y SKU)

INSERT INTO public.inventory (product_id, warehouse_id, quantity)
SELECT 
    (SELECT p.id FROM public.products p WHERE p.sku = t.sku LIMIT 1),
    (SELECT w.id FROM public.warehouses w WHERE w.name ILIKE t.warehouse_name LIMIT 1),
    t.quantity
FROM (VALUES 
('A1-42296', 'Repuestos Tecni Express / Principal ⚒️🏠', 2), 
('A1-42296', 'Repuestos Tienda 2 / SPS Altos V 🏡', 3), 
('A1-42301', 'Repuestos Tecni Express / Principal ⚒️🏠', 4), 
('A1-42330', 'Repuestos Tecni Express / Principal ⚒️🏠', 4), 
('A1-42302', 'Repuestos Tecni Express / Principal ⚒️🏠', 6)
) AS t(sku, warehouse_name, quantity)
WHERE (SELECT p.id FROM public.products p WHERE p.sku = t.sku) IS NOT NULL
  AND (SELECT w.id FROM public.warehouses w WHERE w.name ILIKE t.warehouse_name) IS NOT NULL
ON CONFLICT (product_id, warehouse_id) 
DO UPDATE SET quantity = EXCLUDED.quantity;
