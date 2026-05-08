import pandas as pd
import sys

# Forzar utf-8 para stdout
sys.stdout.reconfigure(encoding='utf-8')

EXCEL_PATH = 'docs/data/products_tecni_express_2026_05_07_15_36_13.xls'

def count_tecniexpress():
    df = pd.read_excel(EXCEL_PATH)
    df.columns = [c.strip() for c in df.columns]
    
    tiendas_tecni = df[df['Tienda'].astype(str).str.contains('tecni', case=False, na=False)]
    
    print(f"\nRegistros en tiendas 'tecni': {len(tiendas_tecni)}")
    
    con_imagen = tiendas_tecni[tiendas_tecni['Image Link'].notna() & (tiendas_tecni['Image Link'].str.strip() != '')]
    print(f"Registros en tiendas 'tecni' con CÓDIGO de imagen: {len(con_imagen)}")
    
    import uuid, re
    NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
    def slugify(text):
        text = str(text).lower()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_-]+', '-', text)
        return text.strip('-')
        
    unique_slugs = set()
    for _, row in con_imagen.iterrows():
        name = row.get('Artículo')
        raw_sku = row.get('Código de barras')
        if not name or pd.isna(name): continue
        sku_str = str(raw_sku).strip() if pd.notna(raw_sku) and str(raw_sku).strip() else f"NO-SKU-{str(uuid.uuid5(NAMESPACE, str(name)))[:8].upper()}"
        unique_slugs.add(slugify(f"{name} {sku_str}"))
        
    print(f"Productos únicos en tiendas 'tecni' con CÓDIGO de imagen: {len(unique_slugs)}")

if __name__ == '__main__':
    count_tecniexpress()
