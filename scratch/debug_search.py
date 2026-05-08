# pyrefly: ignore [missing-import]
import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from supabase import create_client

load_dotenv()

url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(url, key)

def debug_search():
    query = "teclado pausa"
    print(f"Buscando: '{query}'")
    
    # Intentar con la RPC directamente
    try:
        res = supabase.rpc("search_products_fts", {
            "p_query": query,
            "p_brand_name": None,
            "p_limit": 5
        }).execute()
        
        print(f"Resultados de RPC search_products_fts: {len(res.data)}")
        for r in res.data:
            print(f" - [{r['sku']}] {r['name_es']}")
            
    except Exception as e:
        print(f"Error en RPC search_products_fts: {e}")

    # Buscar con ILIKE para ver si el producto existe
    try:
        res_ilike = supabase.table("products").select("name_es, sku").ilike("name_es", "%teclado%pausa%").execute()
        print(f"\nResultados de ILIKE '%teclado%pausa%': {len(res_ilike.data)}")
        for r in res_ilike.data:
            print(f" - [{r['sku']}] {r['name_es']}")
    except Exception as e:
        print(f"Error en ILIKE: {e}")

if __name__ == '__main__':
    debug_search()
