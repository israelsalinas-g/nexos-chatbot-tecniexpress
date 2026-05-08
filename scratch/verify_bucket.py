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

def verify_bucket():
    print("Verificando el bucket 'product-images' en Supabase Storage...")
    
    # Listamos el contenido de la raíz del bucket (serán las carpetas de los product_ids)
    try:
        folders = supabase.storage.from_("product-images").list()
        
        if not folders:
            print("El bucket parece estar vacío.")
            return
            
        print(f"Se encontraron {len(folders)} carpetas de productos en la raíz del bucket.")
        
        # Revisamos la primera carpeta para ver si tiene un archivo dentro
        first_folder = folders[0]['name']
        files = supabase.storage.from_("product-images").list(first_folder)
        
        print(f"Ejemplo: Dentro de la carpeta '{first_folder}' hay {len(files)} archivo(s).")
        if files:
            print(f" - Archivo encontrado: {files[0]['name']}")
            
    except Exception as e:
        print(f"Error accediendo al bucket: {str(e)}")

if __name__ == '__main__':
    verify_bucket()
