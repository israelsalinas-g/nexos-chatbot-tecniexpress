import pandas as pd
import uuid
import re
from pathlib import Path

# Configuración de rutas
BASE_DIR = Path(__file__).parent.parent
EXCEL_PATH = BASE_DIR / 'docs' / 'data' / 'products_tecni_express_2026_05_07_15_36_13.xls'
OUTPUT_SQL = BASE_DIR / 'supabase' / 'seed.sql'

# Namespace para UUIDs determinísticos
NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')

def get_uuid(name):
    return str(uuid.uuid5(NAMESPACE, str(name)))

def slugify(text):
    text = str(text).lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')

def clean_sql_value(val):
    if pd.isna(val):
        return 'NULL'
    if isinstance(val, str):
        val = val.replace("'", "''")
        return f"'{val}'"
    return str(val)

def generate_seed():
    print(f"Leyendo Excel: {EXCEL_PATH}")
    df = pd.read_excel(EXCEL_PATH)
    df.columns = [c.strip() for c in df.columns]
    
    sql_lines = ["-- Seed optimizado con Batch Inserts", ""]

    # --- 1. BRANDS ---
    print("Batching Marcas...")
    raw_brands = df['Tags'].str.split('|').str[0].dropna().unique()
    brand_values = []
    for b in raw_brands:
        brand_values.append(f"INSERT INTO public.brands (name, slug) SELECT {clean_sql_value(b)}, '{slugify(b)}' WHERE NOT EXISTS (SELECT 1 FROM public.brands WHERE name ILIKE {clean_sql_value(b)});")
    if brand_values:
        sql_lines.extend(brand_values)

    # --- 2. CATEGORIES ---
    print("Batching Categorías...")
    cat_values = ["INSERT INTO public.categories (name_es, name_en, slug) SELECT 'Otros', 'Otros', 'otros' WHERE NOT EXISTS (SELECT 1 FROM public.categories WHERE slug = 'otros');"]
    sql_lines.extend(cat_values)

    # --- 3. WAREHOUSES ---
    print("Batching Bodegas...")
    raw_warehouses = df['Tienda'].dropna().unique()
    wh_values = []
    for w in raw_warehouses:
        wh_values.append(f"INSERT INTO public.warehouses (name) SELECT {clean_sql_value(w)} WHERE NOT EXISTS (SELECT 1 FROM public.warehouses WHERE name ILIKE {clean_sql_value(w)});")
    if wh_values:
        sql_lines.extend(wh_values)

    # --- 4. PRODUCTS & INVENTORY ---
    print("Batching Productos e Inventario...")
    product_values = []
    image_values = []
    inventory_values = []
    
    sku_to_slug = {}
    slug_seen = set()

    for _, row in df.iterrows():
        name = row.get('Artículo')
        raw_sku = row.get('Código de barras')
        if not name or pd.isna(name): continue
        
        sku_str = str(raw_sku).strip() if pd.notna(raw_sku) and str(raw_sku).strip() else None
        
        # Generar SKU de respaldo si está vacío (la base de datos exige que no sea NULL)
        if not sku_str:
            sku_str = f"NO-SKU-{str(uuid.uuid5(NAMESPACE, str(name)))[:8].upper()}"
        
        # Deduplicación por SKU
        if sku_str and sku_str in sku_to_slug:
            p_slug = sku_to_slug[sku_str]
            is_new_product = False
        else:
            p_slug = slugify(f"{name} {sku_str}")
            # Si el slug ya existe por nombre duplicado (sin SKU), le agregamos un sufijo
            original_slug = p_slug
            counter = 1
            while p_slug in slug_seen:
                p_slug = f"{original_slug}-{counter}"
                counter += 1
                
            slug_seen.add(p_slug)
            if sku_str:
                sku_to_slug[sku_str] = p_slug
            is_new_product = True

        if is_new_product:
            tag_brand = str(row.get('Tags', '')).split('|')[0]
            b_id = f"(SELECT id FROM public.brands WHERE name ILIKE {clean_sql_value(tag_brand)} LIMIT 1)" if tag_brand and pd.notna(tag_brand) else 'NULL'
            
            c_id = "(SELECT id FROM public.categories WHERE slug = 'otros' LIMIT 1)"
            p_location = row.get('Grupo')
            p_location_sql = clean_sql_value(p_location) if pd.notna(p_location) else 'NULL'
            
            tags_list = [t.strip() for t in str(row.get('Tags', '')).split('|')] if pd.notna(row.get('Tags')) else []
            tags_sql = "ARRAY[" + ", ".join([f"'{t}'" for t in tags_list]) + "]" if tags_list else "NULL"
            
            p_public = int(row.get('Precio de venta', 0) * 100) if pd.notna(row.get('Precio de venta')) else 0
            p_tech = int(row.get('Precio de tecnico', 0) * 100) if pd.notna(row.get('Precio de tecnico')) else 0
            p_wholesale = int(row.get('Precio Mayoreo', 0) * 100) if pd.notna(row.get('Precio Mayoreo')) else 0
            p_name_en = clean_sql_value(name)

            sku_sql_val = f"'{sku_str}'" if sku_str else "NULL"
            product_values.append(f"({clean_sql_value(name)}, {p_name_en}, '{p_slug}', {sku_sql_val}, {p_public}, {p_tech}, {p_wholesale}, {b_id}, {c_id}, {p_location_sql}, {tags_sql})")
            
        # Imágenes e Inventario se procesan siempre, usando el p_slug (sea nuevo o ya existente)
        img_url = row.get('Image Link')
        if pd.notna(img_url) and str(img_url).strip():
            img_sql = f"INSERT INTO public.product_images (product_id, url, storage_path, is_primary) SELECT id, {clean_sql_value(img_url)}, 'external/' || id, true FROM public.products WHERE slug = '{p_slug}' ON CONFLICT DO NOTHING;"
            image_values.append(img_sql)

        w_name = row.get('Tienda')
        if pd.notna(w_name) and str(w_name).strip():
            qty = int(row.get('Cantidad', 0)) if pd.notna(row.get('Cantidad')) else 0
            inv_sql = f"INSERT INTO public.inventory (product_id, warehouse_id, quantity) SELECT p.id, w.id, {qty} FROM public.products p, public.warehouses w WHERE p.slug = '{p_slug}' AND w.name ILIKE {clean_sql_value(w_name)} ON CONFLICT (product_id, warehouse_id) DO UPDATE SET quantity = EXCLUDED.quantity;"
            inventory_values.append(inv_sql)

    # --- Generación de Archivos Particionados ---
    out_dir = BASE_DIR / 'supabase' / 'seed_parts_excel'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Archivo 1: Marcas y Categorías y Bodegas
    with open(out_dir / '01_base.sql', 'w', encoding='utf-8') as f:
        f.write("-- Base Data\n" + "\n".join(sql_lines))
        
    # Archivo 2..N: Productos
    file_idx = 2
    batch_size = 300
    for i in range(0, len(product_values), batch_size):
        batch = product_values[i:i+batch_size]
        content = f"-- Productos Batch {file_idx-1}\n"
        content += f"INSERT INTO public.products (name_es, name_en, slug, sku, price_public, price_technician, price_wholesale, brand_id, category_id, location, tags) VALUES\n"
        content += ",\n".join(batch)
        content += "\nON CONFLICT (sku) DO UPDATE SET price_public = EXCLUDED.price_public;\n"
        with open(out_dir / f'{file_idx:02d}_products.sql', 'w', encoding='utf-8') as f:
            f.write(content)
        file_idx += 1

    # Archivo N+1: Imágenes
    img_content = "-- Imágenes\n"
    img_content += "\n".join(image_values)
    with open(out_dir / f'{file_idx:02d}_images.sql', 'w', encoding='utf-8') as f:
        f.write(img_content)
    file_idx += 1

    # Archivo N+2: Inventario
    inv_content = "-- Inventario\n"
    inv_content += "\n".join(inventory_values)
    with open(out_dir / f'{file_idx:02d}_inventory.sql', 'w', encoding='utf-8') as f:
        f.write(inv_content)

    print(f"Seed dividido en {file_idx} archivos en la carpeta: {out_dir}")

if __name__ == "__main__":
    generate_seed()

