import os
# pyrefly: ignore [missing-import]
import httpx
import uuid
import mimetypes
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from supabase import create_client, Client

# Cargar variables de entorno desde .env
load_dotenv()

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Error: NEXT_PUBLIC_SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY deben estar en el archivo .env")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
BUCKET_NAME = "product-images"

def migrate_images():
    print(f"Iniciando migración de imágenes al bucket '{BUCKET_NAME}' en Supabase...")
    
    # Obtener todas las imágenes
    response = supabase.table("product_images").select("*").execute()
    
    images = response.data
    if not images:
        print("No se encontraron imágenes externas para migrar (o la tabla está vacía).")
        return

    import time
    
    # Headers para parecer un navegador
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    print(f"Se encontraron {len(images)} imágenes para migrar.")
    
    # Usar cliente HTTP para descargar
    with httpx.Client(timeout=30.0, follow_redirects=True, headers=headers) as client:
        for img in images:
            img_id = img["id"]
            product_id = img["product_id"]
            external_url = img["url"]
            
            # Skip si ya es una imagen migrada
            if SUPABASE_URL in external_url or not external_url.startswith("http"):
                continue
            
            print(f"Procesando [{img_id}]: {external_url}")
            
            success = False
            for attempt in range(3): # 3 Intentos
                try:
                    # Descargar la imagen
                    res = client.get(external_url)
                    res.raise_for_status()
                    
                    # Determinar extensión
                    content_type = res.headers.get('content-type', 'image/jpeg')
                    ext = mimetypes.guess_extension(content_type) or '.jpg'
                    if ext == '.jpe': ext = '.jpg'
                    
                    # Definir ruta en Supabase Storage
                    new_storage_path = f"{product_id}/{img_id}{ext}"
                    
                    # Subir archivo al bucket
                    file_bytes = res.content
                    supabase.storage.from_(BUCKET_NAME).upload(
                        file=file_bytes,
                        path=new_storage_path,
                        file_options={"content-type": content_type, "upsert": "true"}
                    )
                    
                    # Obtener la URL pública oficial
                    public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(new_storage_path)
                    
                    # Actualizar el registro en la base de datos
                    supabase.table("product_images").update({
                        "url": public_url,
                        "storage_path": new_storage_path
                    }).eq("id", img_id).execute()
                    
                    print(f" OK -> {public_url}")
                    success = True
                    break # Salir del loop de reintentos
                    
                except Exception as e:
                    print(f" Intento {attempt + 1} fallido: {str(e)}")
                    time.sleep(1) # Esperar un poco antes de reintentar
            
            if not success:
                print(f" ERROR definitivo procesando {img_id}")
            
            time.sleep(0.5) # Pausa cortés para evitar bloqueos (Rate Limiting)

    print("Migración completada.")

if __name__ == "__main__":
    migrate_images()
