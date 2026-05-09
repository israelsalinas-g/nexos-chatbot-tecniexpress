import io
import logging
# pyrefly: ignore [missing-import]
from PIL import Image

logger = logging.getLogger(__name__)

# Singleton para el modelo
_MODEL = None
_PROCESSOR = None
_DEVICE = None

def _load_model():
    global _MODEL, _PROCESSOR, _DEVICE
    if _MODEL is not None:
        return True
    
    try:
        # pyrefly: ignore [missing-import]
        import torch
        # pyrefly: ignore [missing-import]
        import open_clip
        logger.info("[clip_service] Cargando modelo CLIP (open-clip-torch)...")
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")
        model.eval()
        device = "cpu" # Forzamos CPU para estabilidad en Windows y ahorro en Railway
        model.to(device)
        
        _MODEL = model
        _PROCESSOR = preprocess
        _DEVICE = device
        logger.info(f"[clip_service] Modelo CLIP listo en {_DEVICE}.")
        return True
    except Exception as e:
        logger.warning(f"[clip_service] No se pudo cargar CLIP: {e}")
        return False

def get_image_embedding(image_bytes: bytes) -> list[float]:
    """
    Genera un embedding CLIP normalizado de 512 dimensiones.
    Carga el modelo perezosamente (lazy load).
    """
    if not _load_model():
        return []

    try:
        # pyrefly: ignore [missing-import]
        import torch
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = _PROCESSOR(image).unsqueeze(0).to(_DEVICE)
        
        with torch.no_grad():
            feats = _MODEL.encode_image(tensor)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            
        return feats.squeeze(0).cpu().tolist()
    except Exception as exc:
        logger.error(f"[clip_service] Error generando embedding: {exc}")
        return []
