"""
Genera y almacena embeddings CLIP para todas las imágenes de productos.

Uso:
    python scripts/populate_clip_embeddings.py [--force]

Opciones:
    --force   Re-genera embeddings aunque ya existan.

Requiere en .env:
    NEXT_PUBLIC_SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY
"""

import os
import sys
import time
import logging
from pathlib import Path

# Permite importar bot.services desde la raíz del proyecto
sys.path.insert(0, str(Path(__file__).parent.parent))

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

# pyrefly: ignore [missing-import]
import httpx
from supabase import create_client, Client

# Cargar modelo CLIP (ocurre una sola vez al importar)
from bot.services.clip_service import get_image_embedding

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
FORCE = "--force" in sys.argv

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("Faltan NEXT_PUBLIC_SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_existing_image_ids() -> set[str]:
    r = supabase.table("product_image_embeddings").select("product_image_id").execute()
    return {row["product_image_id"] for row in (r.data or [])}


def fetch_all_product_images() -> list[dict]:
    r = supabase.table("product_images").select("id, product_id, url").execute()
    return r.data or []


def upsert_embedding(product_id: str, product_image_id: str, image_url: str, embedding: list[float]) -> None:
    supabase.table("product_image_embeddings").upsert(
        {
            "product_id": product_id,
            "product_image_id": product_image_id,
            "image_url": image_url,
            "embedding": embedding,
            "model_version": "clip-vit-base-patch32",
        },
        on_conflict="product_image_id",
    ).execute()


def run() -> None:
    images = fetch_all_product_images()
    logger.info(f"Total imágenes en catálogo: {len(images)}")

    existing_ids = set() if FORCE else fetch_existing_image_ids()
    logger.info(f"Ya tienen embedding: {len(existing_ids)}{'  (ignorando con --force)' if FORCE else ''}")

    to_process = [img for img in images if img["id"] not in existing_ids]
    logger.info(f"A procesar: {len(to_process)}")

    if not to_process:
        logger.info("Nada que hacer. Usa --force para re-generar todos.")
        return

    ok = errors = skipped = 0
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
    }

    with httpx.Client(follow_redirects=True, headers=headers, timeout=30) as client:
        for idx, img in enumerate(to_process, 1):
            img_id = img["id"]
            product_id = img["product_id"]
            url = img.get("url", "")

            if not url:
                logger.warning(f"[{idx}/{len(to_process)}] Sin URL: {img_id}, saltando.")
                skipped += 1
                continue

            try:
                logger.info(f"[{idx}/{len(to_process)}] {img_id} — {url[:80]}")
                resp = client.get(url)
                resp.raise_for_status()
                image_bytes = resp.content
                embedding = get_image_embedding(image_bytes)
                upsert_embedding(product_id, img_id, url, embedding)
                ok += 1
            except Exception as exc:
                logger.error(f"  ERROR: {exc}")
                errors += 1

            time.sleep(0.3)

    logger.info(f"Completado — OK: {ok} | Errores: {errors} | Saltados: {skipped}")


if __name__ == "__main__":
    run()
