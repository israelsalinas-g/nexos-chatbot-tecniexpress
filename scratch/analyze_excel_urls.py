import pandas as pd

EXCEL_PATH = 'docs/data/products_tecni_express_2026_05_07_15_36_13.xls'

def analyze_excel_urls():
    df = pd.read_excel(EXCEL_PATH)
    df.columns = [c.strip() for c in df.columns]
    
    # Todos los registros con Image Link no nulo
    has_image = df[df['Image Link'].notna()]
    total_has_image = len(has_image)
    
    # De esos, cuántos empiezan con http o https
    valid_urls = has_image[has_image['Image Link'].str.startswith(('http://', 'https://'), na=False)]
    total_valid = len(valid_urls)
    
    print(f"Total registros con 'Image Link': {total_has_image}")
    print(f"Total registros con URL válida (http/https): {total_valid}")
    print(f"Total registros con URL basura: {total_has_image - total_valid}")
    
    print("\nEjemplos de URLs válidas:")
    print(valid_urls['Image Link'].head(5).tolist())
    
    print("\nEjemplos de URLs basura:")
    invalid_urls = has_image[~has_image['Image Link'].str.startswith(('http://', 'https://'), na=False)]
    print(invalid_urls['Image Link'].head(10).tolist())

if __name__ == '__main__':
    analyze_excel_urls()
