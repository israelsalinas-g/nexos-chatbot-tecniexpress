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
    brand_map = {}
    brand_values = []
    for b in raw_brands:
        b_id = get_uuid(f"brand:{b}")
        brand_map[b] = b_id
        brand_values.append(f"('{b_id}', {clean_sql_value(b)}, '{slugify(b)}')")
    
    if brand_values:
        sql_lines.append(f"INSERT INTO public.brands (id, name, slug) VALUES " + ", ".join(brand_values) + " ON CONFLICT (id) DO NOTHING;")

    # --- 2. CATEGORIES ---
    print("Batching Categorías...")
    raw_categories = df['Grupo'].dropna().unique()
    category_map = {}
    cat_values = []
    for c in raw_categories:
        c_id = get_uuid(f"cat:{c}")
        category_map[c] = c_id
        cat_values.append(f"('{c_id}', {clean_sql_value(c)}, '{slugify(c)}')")
    
    if cat_values:
        sql_lines.append(f"\nINSERT INTO public.categories (id, name_es, slug) VALUES " + ", ".join(cat_values) + " ON CONFLICT (id) DO NOTHING;")

    # --- 3. WAREHOUSES ---
    print("Batching Bodegas...")
    raw_warehouses = df['Tienda'].dropna().unique()
    warehouse_map = {}
    wh_values = []
    for w in raw_warehouses:
        w_id = get_uuid(f"wh:{w}")
        warehouse_map[w] = w_id
        wh_values.append(f"('{w_id}', {clean_sql_value(w)})")
    
    if wh_values:
        sql_lines.append(f"\nINSERT INTO public.warehouses (id, name) VALUES " + ", ".join(wh_values) + " ON CONFLICT (id) DO NOTHING;")

    # --- 4. PRODUCTS & INVENTORY ---
    print("Batching Productos e Inventario...")
    product_values = []
    image_values = []
    inventory_values = []
    product_seen = {}

    for _, row in df.iterrows():
        name = row.get('Artículo')
        sku = row.get('Código de barras')
        if not name: continue
        
        p_id = get_uuid(f"prod:{name}:{sku}")
        
        if p_id not in product_seen:
            product_seen[p_id] = True
            tag_brand = str(row.get('Tags', '')).split('|')[0]
            b_id = f"'{brand_map[tag_brand]}'" if tag_brand in brand_map else 'NULL'
            c_name = row.get('Grupo')
            c_id = f"'{category_map[c_name]}'" if c_name in category_map else 'NULL'
            
            tags_list = [t.strip() for t in str(row.get('Tags', '')).split('|')] if pd.notna(row.get('Tags')) else []
            tags_sql = "ARRAY[" + ", ".join([f"'{t}'" for t in tags_list]) + "]" if tags_list else "NULL"
            
            p_public = int(row.get('Precio de venta', 0) * 100) if pd.notna(row.get('Precio de venta')) else 0
            p_tech = int(row.get('Precio de tecnico', 0) * 100) if pd.notna(row.get('Precio de tecnico')) else 0
            p_wholesale = int(row.get('Precio Mayoreo', 0) * 100) if pd.notna(row.get('Precio Mayoreo')) else 0

            product_values.append(f"('{p_id}', {clean_sql_value(name)}, {clean_sql_value(sku)}, {p_public}, {p_tech}, {p_wholesale}, {b_id}, {c_id}, {tags_sql})")
            
            img_url = row.get('Image Link')
            if pd.notna(img_url):
                img_id = get_uuid(f"img:{p_id}:{img_url}")
                image_values.append(f"('{img_id}', '{p_id}', {clean_sql_value(img_url)}, true)")

        w_name = row.get('Tienda')
        if w_name in warehouse_map:
            w_id = warehouse_map[w_name]
            qty = int(row.get('Cantidad', 0)) if pd.notna(row.get('Cantidad')) else 0
            inv_id = get_uuid(f"inv:{p_id}:{w_id}")
            inventory_values.append(f"('{inv_id}', '{p_id}', '{w_id}', {qty})")

    # Escribir Productos en batches de 100
    for i in range(0, len(product_values), 100):
        batch = product_values[i:i+100]
        sql_lines.append(f"\nINSERT INTO public.products (id, name_es, sku, price_public, price_technician, price_wholesale, brand_id, category_id, tags) VALUES " + ", ".join(batch) + "\nON CONFLICT (id) DO UPDATE SET price_public = EXCLUDED.price_public, price_technician = EXCLUDED.price_technician, price_wholesale = EXCLUDED.price_wholesale;")

    # Escribir Imágenes en batches de 100
    for i in range(0, len(image_values), 100):
        batch = image_values[i:i+100]
        sql_lines.append(f"\nINSERT INTO public.product_images (id, product_id, url, is_primary) VALUES " + ", ".join(batch) + "\nON CONFLICT (id) DO NOTHING;")

    # Escribir Inventario en batches de 100
    for i in range(0, len(inventory_values), 100):
        batch = inventory_values[i:i+100]
        sql_lines.append(f"\nINSERT INTO public.inventory (id, product_id, warehouse_id, quantity) VALUES " + ", ".join(batch) + "\nON CONFLICT (id) DO UPDATE SET quantity = EXCLUDED.quantity;")

    with open(OUTPUT_SQL, 'w', encoding='utf-8') as f:
        f.write("\n".join(sql_lines))
    print(f"Seed generado con éxito en: {OUTPUT_SQL}")

if __name__ == "__main__":
    generate_seed()
