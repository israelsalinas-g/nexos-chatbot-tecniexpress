"""
claude_service.py — Integración con Anthropic Claude

Funciones:
  - analyze_image()       → extrae info estructurada de una foto
  - analyze_text()        → normaliza descripción de texto del cliente
  - generate_response()   → respuesta natural con resultados de búsqueda
  - extract_from_manual() → extrae código/precio de fragmento de manual PDF
  - search_manufacturer_web() → busca en sitios oficiales del fabricante
"""
import anthropic
import httpx
import base64
import json
import logging
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)
client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# ── Prompt base para extracción estructurada ──────────────────────────────────
EXTRACT_SYSTEM = """Eres un experto en repuestos de lavadoras y secadoras de las marcas
LG, Samsung, Mabe, Whirlpool y Frigidaire.

Tu trabajo es analizar la solicitud del cliente y extraer información estructurada.
RESPONDE ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin markdown.

Campos a extraer:
{
  "marca":              "LG | Samsung | Mabe | Whirlpool | Frigidaire | null",
  "tipo_equipo":        "lavadora | secadora | null",
  "modelo":             "número de modelo exacto si se menciona, sino null",
  "tipo_pieza":         "nombre genérico de la pieza (ej: perilla, motor, correa, bomba, sensor, tablero)",
  "descripcion_busqueda": "frase corta en español para buscar en base de datos (ej: perilla temperatura LG)",
  "codigo_parte":       "si el cliente proporcionó un código exacto, sino null",
  "confianza":          "alta | media | baja"
}"""

# ── 1. Análisis de imagen ─────────────────────────────────────────────────────
async def analyze_image(photo_url: str, caption: Optional[str] = None) -> dict:
    """Analiza foto de repuesto con Claude Vision."""
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.get(photo_url)
            img_b64 = base64.standard_b64encode(resp.content).decode()
            media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0]

        user_text = "Analiza esta imagen de un repuesto de electrodoméstico y extrae la información."
        if caption:
            user_text += f'\nEl cliente también escribió: "{caption}"'

        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=400,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
                {"type": "text", "text": user_text},
            ]}],
        )
        return json.loads(msg.content[0].text)
    except json.JSONDecodeError:
        logger.warning("analyze_image: JSON parse failed, using caption as fallback")
        return {"descripcion_busqueda": caption or "repuesto", "confianza": "baja",
                "marca": None, "modelo": None, "tipo_pieza": None, "codigo_parte": None}
    except Exception as e:
        logger.error(f"analyze_image: {e}")
        return {"descripcion_busqueda": caption or "repuesto", "confianza": "baja",
                "marca": None, "modelo": None, "tipo_pieza": None, "codigo_parte": None}

# ── 2. Análisis de texto ──────────────────────────────────────────────────────
async def analyze_text(text: str) -> dict:
    """Extrae información estructurada de descripción de texto libre."""
    try:
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=300,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content":
                f'El cliente busca: "{text}"\n\nExtrae la información estructurada en JSON.'}],
        )
        return json.loads(msg.content[0].text)
    except json.JSONDecodeError:
        return {"descripcion_busqueda": text, "confianza": "baja",
                "marca": None, "modelo": None, "tipo_pieza": None, "codigo_parte": None}
    except Exception as e:
        logger.error(f"analyze_text: {e}")
        return {"descripcion_busqueda": text, "confianza": "baja",
                "marca": None, "modelo": None, "tipo_pieza": None, "codigo_parte": None}

# ── 3. Generar respuesta al cliente ───────────────────────────────────────────
async def generate_response(
    products: list,
    query_info: dict,
    history: list,
    source: str = "catálogo",
) -> str:
    """Genera respuesta natural para el cliente con los resultados encontrados."""
    context = (
        f"Fuente: {source}\n"
        f"Solicitud del cliente: {query_info.get('descripcion_busqueda', '')}\n"
        f"Resultados encontrados ({len(products)}):\n"
        + json.dumps(products[:3], ensure_ascii=False, default=str, indent=2)
    )
    recent = history[-4:]  # últimos 2 intercambios
    try:
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=600,
            system="""Eres el asistente de ventas de TecniExpress, tienda de repuestos para
lavadoras y secadoras. Responde en español, de forma amigable y directa.
Muestra los resultados con: nombre, SKU/código, precio y disponibilidad (stock).
Si hay varios resultados, presenta los 3 primeros.
Usa emojis con moderación. Nunca inventes precios ni códigos.""",
            messages=recent + [{"role": "user", "content": context}],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error(f"generate_response: {e}")
        # Respuesta de emergencia sin IA
        if not products:
            return "😔 No encontré ese repuesto en nuestro catálogo. Buscando en manuales..."
        p = products[0]
        stock_txt = "✅ En stock" if p.get("in_stock") else "⚠️ Sin stock"
        return (
            f"🔧 *{p.get('name')}*\n"
            f"SKU: `{p.get('sku')}` | Parte: `{p.get('part_number')}`\n"
            f"💰 ${p.get('price'):,} | {stock_txt}\n"
            f"Marca: {p.get('brand')}"
        )

# ── 4. Extraer código de parte desde texto de manual PDF ─────────────────────
async def extract_from_manual(relevant_text: str, query_info: dict) -> str:
    """
    Dado un fragmento de manual, extrae código de parte, descripción y precio.
    """
    pieza = query_info.get("tipo_pieza", "")
    modelo = query_info.get("modelo", "")
    try:
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=500,
            system="""Eres un experto en manuales técnicos de electrodomésticos.
Extrae del texto del manual: código de parte, nombre oficial, y precio de lista si aparece.
Responde en español, de forma concisa.""",
            messages=[{"role": "user", "content":
                f"Busco el repuesto: {pieza} para modelo {modelo}\n\n"
                f"Fragmento del manual:\n{relevant_text}\n\n"
                f"¿Cuál es el código de parte y precio? Si no está claro, indícalo."}],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error(f"extract_from_manual: {e}")
        return "No se pudo extraer información del manual."

# ── 5. Buscar en sitios web del fabricante ───────────────────────────────────
MANUFACTURER_URLS = {
    "lg":        "https://www.lg.com/us/support/parts",
    "samsung":   "https://www.samsung.com/us/home-appliances/washers/",
    "whirlpool": "https://www.whirlpoolparts.com",
    "mabe":      "https://www.mabe.com.mx/refacciones",
    "frigidaire":"https://www.frigidaire.com/Parts-and-Accessories/",
}

async def search_manufacturer_web(query_info: dict) -> str:
    """Genera instrucciones de búsqueda en sitio web del fabricante."""
    marca = (query_info.get("marca") or "").lower()
    modelo = query_info.get("modelo", "")
    pieza = query_info.get("tipo_pieza", "")
    descripcion = query_info.get("descripcion_busqueda", "")
    url = MANUFACTURER_URLS.get(marca, "")

    try:
        msg = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=400,
            system="""Eres un experto en repuestos de electrodomésticos.
Dado el repuesto que busca el cliente, proporciona:
1. Código de parte probable (basado en tu conocimiento)
2. URL o instrucciones para encontrarlo en el sitio oficial
3. Rango de precio aproximado si lo conoces
Responde en español, de forma clara y útil.""",
            messages=[{"role": "user", "content":
                f"El cliente necesita: {descripcion}\n"
                f"Marca: {marca} | Modelo: {modelo} | Pieza: {pieza}\n"
                f"Sitio oficial: {url}\n\n"
                f"¿Cuál sería el código de parte y dónde buscarlo?"}],
        )
        return msg.content[0].text
    except Exception as e:
        logger.error(f"search_manufacturer_web: {e}")
        return f"Puedes buscar este repuesto en {url} usando el modelo {modelo}."
