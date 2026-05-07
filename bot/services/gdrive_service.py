"""
gdrive_service.py — Búsqueda en manuales PDF de Google Drive (acceso directo)

No requiere pre-indexación. Busca el PDF del modelo en Drive al momento de la consulta.
Requiere: GOOGLE_SERVICE_ACCOUNT_JSON configurado en .env
"""
import io
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _drive_client():
    """Crea cliente de Drive API usando service account JSON."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from bot.config import GOOGLE_SERVICE_ACCOUNT_JSON

    if not GOOGLE_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON no configurado")

    creds_info = (
        json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        if isinstance(GOOGLE_SERVICE_ACCOUNT_JSON, str)
        else GOOGLE_SERVICE_ACCOUNT_JSON
    )
    creds = service_account.Credentials.from_service_account_info(creds_info, scopes=_SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def find_manual_file(brand: str, model: str) -> Optional[str]:
    """
    Busca el PDF del modelo en Google Drive.
    Prefiere archivos cuyo nombre incluye la marca.
    Retorna el file_id del mejor resultado, o None.
    """
    model_clean = model.strip().upper()
    brand_clean = brand.strip().upper() if brand else ""

    query = (
        f"name contains '{model_clean}' "
        f"and mimeType='application/pdf' "
        f"and trashed=false"
    )
    try:
        drive = _drive_client()
        result = drive.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=5,
        ).execute()
        files = result.get("files", [])

        if brand_clean and len(files) > 1:
            brand_files = [f for f in files if brand_clean in f["name"].upper()]
            if brand_files:
                return brand_files[0]["id"]

        return files[0]["id"] if files else None
    except Exception as e:
        logger.error(f"[gdrive] find_manual_file error: {e}")
        return None


def extract_pdf_text(file_id: str, max_pages: int = 30) -> str:
    """Descarga el PDF de Drive y extrae texto con PyMuPDF."""
    try:
        import fitz
        from googleapiclient.http import MediaIoBaseDownload

        drive = _drive_client()
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
        logger.error(f"[gdrive] extract_pdf_text error: {e}")
        return ""


def _find_relevant_chunks(text: str, keywords: list[str], chunk_size: int = 800) -> str:
    """
    Divide el texto del PDF en chunks y retorna los 4 más relevantes
    según cuántas palabras clave contienen.
    """
    if not text:
        return ""
    words_lower = [k.lower() for k in keywords if k]
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    scored = [
        (sum(1 for w in words_lower if w in chunk.lower()), chunk)
        for chunk in chunks
    ]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(reverse=True)
    return "\n---\n".join(c for _, c in scored[:4])


def search_in_manual(
    brand: str,
    model: str,
    part_description: str,
    part_type: Optional[str] = None,
) -> dict:
    """
    Busca un repuesto en el PDF del modelo en Google Drive.

    Retorna dict con:
      found (bool) — se encontraron fragmentos relevantes
      relevant_text (str) — los 4 chunks más relevantes del PDF
      file_id (str | None)
    """
    result = {"found": False, "file_id": None, "relevant_text": "", "source": "gdrive"}

    if not model:
        return result

    file_id = find_manual_file(brand, model)
    if not file_id:
        logger.info(f"[gdrive] No PDF encontrado para {brand} {model}")
        return result

    result["file_id"] = file_id

    text = extract_pdf_text(file_id)
    if not text:
        return result

    keywords = [k for k in [part_description, part_type, model, brand] if k]
    relevant = _find_relevant_chunks(text, keywords)

    if relevant:
        result["found"] = True
        result["relevant_text"] = relevant

    return result
