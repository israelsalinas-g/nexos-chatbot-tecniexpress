import pandas as pd

EXCEL_PATH = 'docs/data/products_tecni_express_2026_05_07_15_36_13.xls'

def analyze_all_columns():
    df = pd.read_excel(EXCEL_PATH)
    df.columns = [c.strip() for c in df.columns]
    
    for col in df.columns:
        valid_urls = df[df[col].astype(str).str.startswith(('http://', 'https://'), na=False)]
        if not valid_urls.empty:
            print(f"Columna '{col}' tiene {len(valid_urls)} URLs válidas.")
            print(valid_urls[col].head(3).tolist())

if __name__ == '__main__':
    analyze_all_columns()
