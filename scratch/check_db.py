import os
# pyrefly: ignore [missing-import]
# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from supabase import create_client

load_dotenv()

url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(url, key)

def check_counts():
    p_count = supabase.table("products").select("id", count="exact").execute().count
    img_count = supabase.table("product_images").select("id", count="exact").execute().count
    
    print(f"Total products in DB: {p_count}")
    print(f"Total images in DB: {img_count}")
    
    # Check a few slugs from the SQL file
    test_slugs = ['acoplador-motor-285753a', 'acoplador-de-motor-whirlpool-285753ap']
    for slug in test_slugs:
        res = supabase.table("products").select("id").eq("slug", slug).execute()
        if res.data:
            print(f"Slug found: {slug}")
        else:
            print(f"Slug NOT found: {slug}")

if __name__ == '__main__':
    check_counts()
