import os
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from supabase import create_client

load_dotenv()

url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(url, key)

def count_unique_products_with_images():
    # Fetch all product_id from product_images
    res = supabase.table("product_images").select("product_id").execute()
    product_ids = set(img['product_id'] for img in res.data)
    
    print(f"Total unique product IDs with images in DB: {len(product_ids)}")
    
    # Let's see some example URLs to see if they are migrated or not
    res_urls = supabase.table("product_images").select("url").limit(5).execute()
    print("Sample URLs:")
    for r in res_urls.data:
        print(f" - {r['url']}")

if __name__ == '__main__':
    count_unique_products_with_images()
