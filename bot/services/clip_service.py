import io
import logging

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger(__name__)

_MODEL_NAME = "openai/clip-vit-base-patch32"

logger.info("[clip_service] Cargando modelo CLIP...")
_processor: CLIPProcessor = CLIPProcessor.from_pretrained(_MODEL_NAME)
_model: CLIPModel = CLIPModel.from_pretrained(_MODEL_NAME)
_model.eval()
_device = "cuda" if torch.cuda.is_available() else "cpu"
_model.to(_device)
logger.info(f"[clip_service] Modelo CLIP listo en {_device}.")


def get_image_embedding(image_bytes: bytes) -> list[float]:
    """
    Genera un embedding CLIP normalizado de 512 dimensiones.
    Retorna una lista de floats lista para pgvector (similitud coseno).
    """
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise ValueError(f"No se pudo decodificar la imagen: {exc}") from exc

    inputs = _processor(images=image, return_tensors="pt").to(_device)
    with torch.no_grad():
        feats = _model.get_image_features(**inputs)

    feats = feats / feats.norm(dim=-1, keepdim=True)
    return feats.squeeze(0).cpu().tolist()
