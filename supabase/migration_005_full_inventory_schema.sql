-- ================================================================
-- Migration 005: Full Inventory Schema (Brands, Categories, Warehouses, Inventory, Images)
-- ================================================================

-- 1. Marcas
CREATE TABLE IF NOT EXISTS public.brands (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    slug text UNIQUE,
    created_at timestamptz DEFAULT now()
);

-- 2. Categorías
CREATE TABLE IF NOT EXISTS public.categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name_es text NOT NULL UNIQUE,
    slug text UNIQUE,
    created_at timestamptz DEFAULT now()
);

-- 3. Bodegas / Tiendas
CREATE TABLE IF NOT EXISTS public.warehouses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    location text,
    created_at timestamptz DEFAULT now()
);

-- 4. Productos (Asegurar campos necesarios)
-- Nota: Si la tabla ya existe, solo agregamos columnas faltantes
CREATE TABLE IF NOT EXISTS public.products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sku text UNIQUE,
    part_number text,
    name_es text NOT NULL,
    description_es text,
    price_public integer DEFAULT 0,
    price_technician integer DEFAULT 0,
    price_wholesale integer DEFAULT 0,
    stock_quantity integer DEFAULT 0, -- Cantidad global (legacy/fallback)
    brand_id uuid REFERENCES public.brands(id),
    category_id uuid REFERENCES public.categories(id),
    is_active boolean DEFAULT true,
    is_featured boolean DEFAULT false,
    compatible_models text[],
    tags text[],
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- 5. Inventario por Bodega (Soporta múltiples tiendas)
CREATE TABLE IF NOT EXISTS public.inventory (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid REFERENCES public.products(id) ON DELETE CASCADE,
    warehouse_id uuid REFERENCES public.warehouses(id) ON DELETE CASCADE,
    quantity integer NOT NULL DEFAULT 0,
    updated_at timestamptz DEFAULT now(),
    UNIQUE(product_id, warehouse_id)
);

-- 6. Galería de Imágenes (Soporta múltiples imágenes)
CREATE TABLE IF NOT EXISTS public.product_images (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id uuid REFERENCES public.products(id) ON DELETE CASCADE,
    url text NOT NULL,
    is_primary boolean DEFAULT false,
    created_at timestamptz DEFAULT now()
);

-- 7. Índices de rendimiento
CREATE INDEX IF NOT EXISTS idx_inventory_product ON public.inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_warehouse ON public.inventory(warehouse_id);
CREATE INDEX IF NOT EXISTS idx_product_images_product ON public.product_images(product_id);

-- 8. Habilitar RLS (Seguridad)
ALTER TABLE public.brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.warehouses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.inventory ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_images ENABLE ROW LEVEL SECURITY;

-- Políticas para permitir lectura pública (o según necesite el bot)
-- El bot usará service_role, por lo que estas políticas son para el cliente web si existe.
CREATE POLICY "Public Read Brands" ON public.brands FOR SELECT USING (true);
CREATE POLICY "Public Read Categories" ON public.categories FOR SELECT USING (true);
CREATE POLICY "Public Read Warehouses" ON public.warehouses FOR SELECT USING (true);
CREATE POLICY "Public Read Products" ON public.products FOR SELECT USING (true);
CREATE POLICY "Public Read Inventory" ON public.inventory FOR SELECT USING (true);
CREATE POLICY "Public Read Product Images" ON public.product_images FOR SELECT USING (true);
