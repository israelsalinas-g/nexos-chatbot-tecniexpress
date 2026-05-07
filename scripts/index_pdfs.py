"""
Script de indexación de manuales PDF desde Google Drive → Supabase.

Uso:
    python scripts/index_pdfs.py

Requiere:
    GOOGLE_SERVICE_ACCOUNT_JSON — JSON del service account
    GOOGLE_DRIVE_FOLDER_ID      — ID de la carpeta en Drive
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

La carpeta de Drive debe estar compartida con el email del service account.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Asegurar que el proyecto raíz esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import fitz  # PyMuPDF
import io

from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
SA_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
FOLDER_ID = os.environ["GOOGLE_DRIVE_FOLDER_ID"]

CHUNK_SIZE_CHARS = 8_000  # Caracteres por chunk (~2 páginas)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_drive_service():
    creds_dict = json.loads(SA_JSON)
    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_pdf_files(service, folder_id: str) -> list[dict]:
    files = []
    page_token = None

    while True:
        resp = service.files().list(
            q=f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false",
            fields="nextPageToken, files(id, name, modifiedTime)",
            pageToken=page_token,
        ).execute()

        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    return files


def download_pdf(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def extract_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_text = []
    for page in doc:
        pages_text.append(page.get_text())
    doc.close()
    return "\n".join(pages_text)


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS) -> list[str]:
    """Divide el texto en chunks respetando párrafos cuando es posible."""
    chunks = []
    while len(text) > chunk_size:
        # Intentar cortar en un salto de línea
        cut = text.rfind("\n", 0, chunk_size)
        if cut == -1:
            cut = chunk_size
        chunks.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        chunks.append(text)
    return chunks


def parse_brand_model(filename: str) -> tuple[str | None, str | None]:
    """
    Extrae marca y prefijo de modelo del nombre del archivo.
    Convención esperada: "LG_WT185W_service_manual.pdf"
    """
    name = Path(filename).stem.replace("-", "_").replace(" ", "_")
    parts = name.split("_")

    brands = ["LG", "Samsung", "Mabe", "GE", "Whirlpool", "Frigidaire"]
    brand = None
    model_prefix = None

    for part in parts:
        if part.upper() in [b.upper() for b in brands]:
            brand = part.upper()
            break

    # El modelo suele ser la segunda parte (alfanumérica con letras y números)
    for part in parts:
        if part == brand:
            continue
        if re.match(r"^[A-Z0-9]{4,}$", part.upper()):
            model_prefix = part.upper()
            break

    return brand, model_prefix


def get_indexed_files() -> dict[str, str]:
    """Devuelve {source_drive_id: updated_at} de los archivos ya indexados."""
    result = (
        supabase.table("manual_index")
        .select("source_drive_id, updated_at")
        .execute()
    )
    return {r["source_drive_id"]: r["updated_at"] for r in (result.data or [])}


def upsert_chunks(chunks: list[str], file: dict, brand: str | None, model_prefix: str | None):
    for i, chunk in enumerate(chunks):
        supabase.table("manual_index").upsert(
            {
                "document_name": file["name"],
                "brand": brand,
                "model_prefix": model_prefix,
                "text_content": chunk,
                "chunk_index": i,
                "source_drive_id": file["id"],
            },
            on_conflict="source_drive_id,chunk_index",
        ).execute()


def delete_old_chunks(file_id: str, new_chunk_count: int):
    """Elimina chunks sobrantes si el documento ahora tiene menos páginas."""
    supabase.table("manual_index").delete().eq(
        "source_drive_id", file_id
    ).gte("chunk_index", new_chunk_count).execute()


def main():
    print("Conectando a Google Drive...")
    service = get_drive_service()

    print(f"Listando archivos PDF en carpeta {FOLDER_ID}...")
    files = list_pdf_files(service, FOLDER_ID)
    print(f"  Encontrados: {len(files)} archivos PDF")

    indexed = get_indexed_files()

    new_count = 0
    updated_count = 0
    skipped_count = 0

    for file in files:
        file_id = file["id"]
        file_name = file["name"]
        drive_modified = file["modifiedTime"]

        if file_id in indexed:
            # Comparar fechas de modificación
            drive_dt = datetime.fromisoformat(drive_modified.replace("Z", "+00:00"))
            indexed_dt = datetime.fromisoformat(indexed[file_id].replace("Z", "+00:00"))
            if drive_dt <= indexed_dt:
                print(f"  ⏭️  Sin cambios: {file_name}")
                skipped_count += 1
                continue
            print(f"  🔄 Actualizando: {file_name}")
            updated_count += 1
        else:
            print(f"  ➕ Nuevo: {file_name}")
            new_count += 1

        try:
            pdf_bytes = download_pdf(service, file_id)
            text = extract_text(pdf_bytes)

            if not text.strip():
                print(f"     ⚠️  Sin texto extraíble (PDF escaneado): {file_name}")
                continue

            chunks = chunk_text(text)
            brand, model_prefix = parse_brand_model(file_name)
            print(f"     Marca: {brand}, Modelo: {model_prefix}, Chunks: {len(chunks)}")

            upsert_chunks(chunks, file, brand, model_prefix)
            delete_old_chunks(file_id, len(chunks))

        except Exception as e:
            print(f"     ❌ Error procesando {file_name}: {e}")

    print(f"\n✅ Indexación completada:")
    print(f"   Nuevos: {new_count}")
    print(f"   Actualizados: {updated_count}")
    print(f"   Sin cambios: {skipped_count}")


if __name__ == "__main__":
    main()
