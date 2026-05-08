import pandas as pd
import uuid
import re

NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')

def slugify(text):
    text = str(text).lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')

def analyze():
    EXCEL_PATH = 'docs/data/products_tecni_express_2026_05_07_15_36_13.xls'
    df = pd.read_excel(EXCEL_PATH)
    df.columns = [c.strip() for c in df.columns]
    
    print(f"Total rows in Excel: {len(df)}")
    
    products_with_images = 0
    unique_slugs_with_images = set()
    
    sku_to_slug = {}
    slug_seen = set()
    
    for _, row in df.iterrows():
        name = row.get('Artículo')
        raw_sku = row.get('Código de barras')
        if not name or pd.isna(name): continue
        
        sku_str = str(raw_sku).strip() if pd.notna(raw_sku) and str(raw_sku).strip() else None
        if not sku_str:
            sku_str = f"NO-SKU-{str(uuid.uuid5(NAMESPACE, str(name)))[:8].upper()}"
            
        if sku_str in sku_to_slug:
            p_slug = sku_to_slug[sku_str]
        else:
            p_slug = slugify(f"{name} {sku_str}")
            original_slug = p_slug
            counter = 1
            while p_slug in slug_seen:
                p_slug = f"{original_slug}-{counter}"
                counter += 1
            slug_seen.add(p_slug)
            sku_to_slug[sku_str] = p_slug
            
        img_url = row.get('Image Link')
        if pd.notna(img_url) and str(img_url).strip():
            unique_slugs_with_images.add(p_slug)
            
    print(f"Unique products (slugs) total: {len(slug_seen)}")
    print(f"Unique products (slugs) with images: {len(unique_slugs_with_images)}")

if __name__ == '__main__':
    analyze()
