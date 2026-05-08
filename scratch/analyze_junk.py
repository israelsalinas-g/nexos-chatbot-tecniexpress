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

def analyze_junk():
    print("Analizando registros basura en product_images...")
    
    # Registros válidos (migrados exitosamente)
    valid_res = supabase.table("product_images").select("id", count="exact").not_("storage_path", "ilike", "external/%").execute()
    
    # Registros inválidos (basura de Excel o que no tenían http)
    invalid_res = supabase.table("product_images").select("id", count="exact").ilike("storage_path", "external/%").execute()
    
    print(f"✅ Imágenes VÁLIDAS en Supabase Storage: {valid_res.count}")
    print(f"🗑️ Imágenes INVÁLIDAS / BASURA (external/): {invalid_res.count}")

if __name__ == '__main__':
    analyze_junk()
