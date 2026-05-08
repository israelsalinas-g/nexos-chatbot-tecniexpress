-- seed_part3_images.sql
-- Imágenes de Productos (VERSIÓN ULTRA-ROBUSTA POR SKU)

INSERT INTO public.product_images (id, product_id, url, storage_path, is_primary)
SELECT 
    t.id::uuid, 
    (SELECT p.id FROM public.products p WHERE p.sku = t.sku LIMIT 1), 
    t.url, 
    'external/' || t.id, 
    t.is_primary 
FROM (VALUES 
('4975440d-c01f-50a1-893c-e6592d3f1db3', 'A1-42296', 'https://m.media-amazon.com/images/I/61k8pU7A-FL._AC_SL1500_.jpg', true),
('f1a1d2e3-b4c5-5678-9012-34567890abcd', 'A1-42301', 'https://m.media-amazon.com/images/I/61Xz-n7f2xL._AC_SL1500_.jpg', true),
('e9a8b7c6-d5e4-3f21-0a9b-8c7d6e5f4a3b', 'A1-42330', 'https://m.media-amazon.com/images/I/61y8Iu3U-fL._AC_SL1200_.jpg', true),
('d2c3b4a5-1e0f-9a8b-7c6d-5e4f3a2b1c0d', 'A1-42302', 'https://m.media-amazon.com/images/I/71Yv8oW-8JL._AC_SL1500_.jpg', true)
) AS t(id, sku, url, is_primary)
WHERE (SELECT p.id FROM public.products p WHERE p.sku = t.sku) IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM public.product_images pi WHERE pi.id = t.id::uuid);
