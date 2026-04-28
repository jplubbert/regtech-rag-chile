"""Cliente OpenAI para embeddings."""

from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


def _client() -> OpenAI:
    return OpenAI()


def embed_text(text: str) -> list[float]:
    """Devuelve el embedding de un texto."""
    resp = _client().embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def embed_batch(texts: list[str], chunk_size: int = 96) -> list[list[float]]:
    """Embeddings de un batch. Trozado para no exceder límites de la API."""
    out: list[list[float]] = []
    for i in range(0, len(texts), chunk_size):
        sub = texts[i : i + chunk_size]
        resp = _client().embeddings.create(model=EMBEDDING_MODEL, input=sub)
        out.extend(d.embedding for d in resp.data)
    return out
