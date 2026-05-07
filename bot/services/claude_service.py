import base64
import json
# pyrefly: ignore [missing-import]
import anthropic
from bot.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from bot.utils.prompts import (
    SYSTEM_PARSE_QUERY,
    SYSTEM_IDENTIFY_PART,
    SYSTEM_READ_LABEL,
    SYSTEM_ANALYZE_MANUAL,
)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

print(f"[claude_service] Inicializado con Key: {ANTHROPIC_API_KEY[:10]}... (Largo: {len(ANTHROPIC_API_KEY)})")


def _parse_json_response(text: str) -> dict:
    """Extrae JSON de la respuesta de Claude, tolerando bloques de código."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return json.loads(text)


def parse_text_query(text: str) -> dict:
    """
    Analiza un mensaje de texto del cliente y extrae la información
    estructurada del repuesto que necesita.

    Returns:
        {part, brand, model, appliance_type, search_terms, confidence}
    """
    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        system=SYSTEM_PARSE_QUERY,
        messages=[{"role": "user", "content": text}],
    )
    return _parse_json_response(response.content[0].text)


def identify_part(image_bytes: bytes, caption: str = "") -> dict:
    """
    Identifica un repuesto a partir de su fotografía.

    Returns:
        {part_type, possible_brands, description_es, part_number_visible,
         search_terms, confidence, needs_more_info, missing_info}
    """
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    user_content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _detect_media_type(image_bytes),
                "data": image_b64,
            },
        },
    ]

    prompt = SYSTEM_IDENTIFY_PART
    if caption:
        prompt += f"\n\nNota del cliente: {caption}"

    user_content.append({"type": "text", "text": prompt})

    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": user_content}],
    )
    return _parse_json_response(response.content[0].text)


def read_label(image_bytes: bytes) -> dict:
    """
    Lee la etiqueta de especificaciones de un electrodoméstico.

    Returns:
        {brand, model, serial_number, appliance_type, confidence}
    """
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": _detect_media_type(image_bytes),
                        "data": image_b64,
                    },
                },
                {"type": "text", "text": SYSTEM_READ_LABEL},
            ],
        }],
    )
    return _parse_json_response(response.content[0].text)


def _detect_media_type(image_bytes: bytes) -> str:
    """Detecta MIME type por magic bytes."""
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # Telegram envía JPEG por defecto


def analyze_manual(excerpt: str, query: str) -> dict:
    """Extrae información estructurada de un fragmento de manual."""
    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        system=SYSTEM_ANALYZE_MANUAL.format(excerpt=excerpt, query=query),
        messages=[{"role": "user", "content": f"Analiza esta consulta: {query}"}],
    )
    return _parse_json_response(response.content[0].text)
