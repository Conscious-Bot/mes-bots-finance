"""Phase A3 — Embedding wrapper for echo chamber resolution (semantic cross-source dedup)."""

import numpy as np

_model = None
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_DIM = 384


def model():
    """Lazy-load sentence-transformer model."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_text(text):
    """Embed a single string. Returns float32 ndarray of dim 384."""
    if not text or not text.strip():
        return np.zeros(_DIM, dtype=np.float32)
    arr = model().encode(text, convert_to_numpy=True, show_progress_bar=False)
    return arr.astype(np.float32)


def embed_batch(texts):
    """Embed N strings. Returns float32 ndarray of shape (N, 384)."""
    arr = model().encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return arr.astype(np.float32)


def serialize(arr):
    """Pack vector to compact bytes for SQLite BLOB storage."""
    return arr.astype(np.float32).tobytes()


def deserialize(blob):
    """Unpack bytes back to float32 ndarray."""
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(a, b):
    """Cosine similarity between two ndarrays."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def model_name():
    return _MODEL_NAME


def dim():
    return _DIM
