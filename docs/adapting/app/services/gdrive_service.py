"""
gdrive_service.py — Búsqueda en manuales PDF de Google Drive

Estructura esperada en Drive:
  /Manuales/
    LG/        ← un PDF por modelo, ej: "WM3500CW.pdf"
    Samsung/
    Mabe/
    Whirlpool/
    Frigidaire/

Flujo:
  1. Localiza el PDF del modelo en Drive (por nombre de archivo)
  2. Descarga el PDF en memoria
  3. Extrae texto con PyMuPDF (fitz)
  4. Envía fragmentos relevantes a Claude para extraer el código de parte
"""
import io
import re
import logging
from typing import Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import fitz  # PyMuPDF

from app.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# ── Cliente Drive ─────────────────────────────────────────────────────────────
def _drive_client():
    import json
    creds_json = settings.google_service_account_json
    if isinstance(creds_json, str):
        creds_info = json.loads(creds_json)
    else:
        creds_info = creds_json
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

# ── Buscar PDF del modelo en Drive ────────────────────────────────────────────
async def find_manual_file(brand: str, model: str) -> Optional[str]:
    """
    Retorna el file_id del PDF que coincida con el modelo.
    Busca en carpeta del fabricante primero, luego globalmente.
    """
    drive = _drive_client()
    model_clean = model.strip().upper()
    brand_clean = brand.strip().upper() if brand else ""

    # Query Drive: nombre contiene el modelo, es PDF
    query = (
        f"name contains '{model_clean}' "
        f"and mimeType='application/pdf' "
        f"and trashed=false"
    )
    try:
        result = drive.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name, parents)",
            pageSize=5,
        ).execute()
        files = result.get("files", [])

        # Preferir archivos en carpeta de la marca
        if brand_clean and len(files) > 1:
            brand_files = [f for f in files if brand_clean in f["name"].upper()]
            if brand_files:
                return brand_files[0]["id"]

        if files:
            return files[0]["id"]
    except Exception as e:
        logger.error(f"find_manual_file error: {e}")
    return None

# ── Descargar y extraer texto del PDF ────────────────────────────────────────
async def extract_pdf_text(file_id: str, max_pages: int = 30) -> str:
    """
    Descarga el PDF de Drive y extrae el texto con PyMuPDF.
    Limita a max_pages para no procesar manuales gigantes enteros.
    """
    drive = _drive_client()
    try:
        request = drive.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)

        doc = fitz.open(stream=buffer.read(), filetype="pdf")
        pages_text = []
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            pages_text.append(page.get_text())
        doc.close()
        return "\n".join(pages_text)
    except Exception as e:
        logger.error(f"extract_pdf_text error: {e}")
        return ""

# ── Buscar fragmentos relevantes en el texto ─────────────────────────────────
def _find_relevant_chunks(text: str, keywords: list[str], chunk_size: int = 800) -> str:
    """
    Divide el texto en chunks y retorna los más relevantes según palabras clave.
    Evita enviar el manual completo a Claude.
    """
    if not text:
        return ""
    words_lower = [k.lower() for k in keywords if k]
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    scored = []
    for chunk in chunks:
        chunk_lower = chunk.lower()
        score = sum(1 for w in words_lower if w in chunk_lower)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(reverse=True)
    # Retornar los 4 chunks más relevantes
    top = [c for _, c in scored[:4]]
    return "\n---\n".join(top)

# ── Función principal: busca repuesto en manuales ────────────────────────────
async def search_in_manual(
    brand: str,
    model: str,
    part_description: str,
    part_type: Optional[str] = None,
) -> dict:
    """
    Busca un repuesto en el PDF del modelo correspondiente en Google Drive.
    Retorna dict con: found(bool), file_name, relevant_text, file_id.
    """
    result = {
        "found": False,
        "file_name": None,
        "file_id": None,
        "relevant_text": "",
        "source": "manual_pdf",
    }

    if not model:
        logger.info("search_in_manual: no model provided")
        return result

    file_id = await find_manual_file(brand, model)
    if not file_id:
        logger.info(f"No PDF encontrado para {brand} {model}")
        return result

    result["file_id"] = file_id

    text = await extract_pdf_text(file_id)
    if not text:
        return result

    # Palabras clave para encontrar los fragmentos relevantes
    keywords = [k for k in [part_description, part_type, model, brand] if k]
    relevant = _find_relevant_chunks(text, keywords)

    if relevant:
        result["found"] = True
        result["relevant_text"] = relevant

    return result


# ── Listar todos los manuales disponibles (para el dashboard) ─────────────────
async def list_available_manuals() -> list[dict]:
    """Lista todos los PDFs en Drive para mostrar en el panel."""
    drive = _drive_client()
    try:
        result = drive.files().list(
            q="mimeType='application/pdf' and trashed=false",
            spaces="drive",
            fields="files(id, name, size, modifiedTime, parents)",
            pageSize=100,
        ).execute()
        return result.get("files", [])
    except Exception as e:
        logger.error(f"list_available_manuals: {e}")
        return []
