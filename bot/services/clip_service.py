import io
import logging

import open_clip
import torch
from PIL import Image

logger = logging.getLogger(__name__)

logger.info("[clip_service] Cargando modelo CLIP (open-clip-torch)...")
_model, _, _preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
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

    tensor = _preprocess(image).unsqueeze(0).to(_device)
    with torch.no_grad():
        feats = _model.encode_image(tensor)
        feats = feats / feats.norm(dim=-1, keepdim=True)

    return feats.squeeze(0).cpu().tolist()
