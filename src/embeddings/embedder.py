from functools import lru_cache
from config.settings import settings

@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(settings.embedding_model, device='cpu')

def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return get_model().encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False).tolist()
