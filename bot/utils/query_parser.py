import re

_BRANDS: dict[str, str] = {
    "lg": "LG",
    "samsung": "Samsung",
    "mabe": "Mabe",
    "ge": "GE",
    "whirlpool": "Whirlpool",
    "frigidaire": "Frigidaire",
    "acros": "Acros",
}

_APPLIANCE_TYPES: dict[str, str] = {
    "lavadora": "washer",
    "washer": "washer",
    "secadora": "dryer",
    "dryer": "dryer",
    "estufa": "stove",
    "cocina": "stove",
    "stove": "stove",
}

# Patrón de modelo: letras (1-5) seguidas de dígitos (3+), ej: WF45, WT7305CW, WTW5000DW
_MODEL_RE = re.compile(r'^[A-Za-z]{1,5}\d{3,}[A-Za-z0-9\-]*$')


def parse_query(text: str) -> dict:
    """
    Extrae marca, tipo de electrodoméstico, modelo y repuesto del texto del cliente,
    sin llamar a ninguna API. Las palabras del repuesto se preservan exactamente como
    las escribió el cliente.
    """
    brand: str | None = None
    appliance_type: str | None = None
    model: str | None = None
    part_words: list[str] = []

    for token in text.split():
        clean = token.strip(".,;:").lower()

        if clean in _BRANDS:
            if brand is None:
                brand = _BRANDS[clean]
            continue

        if clean in _APPLIANCE_TYPES:
            appliance_type = _APPLIANCE_TYPES[clean]
            continue

        if len(token) >= 5 and _MODEL_RE.match(token):
            if model is None:
                model = token
            continue

        part_words.append(token)

    part = " ".join(part_words).strip() or None

    return {
        "part": part,
        "brand": brand,
        "model": model,
        "appliance_type": appliance_type,
        "sku": None,
        "search_terms": part_words,
        "confidence": 1.0,
    }
