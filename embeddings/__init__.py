"""Shared ChromaDB access for the two embedding pipelines.

Both text_embed and image_embed need the same persistent client pointed at the
same directory, so it is created once here rather than in each module.
"""

from pathlib import Path

import chromadb
from chromadb.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHROMA_PATH = PROJECT_ROOT / "embeddings" / "chroma_store"

TEXT_COLLECTION = "text_descriptions"
IMAGE_COLLECTION = "image_embeddings"

_client = None


def get_chroma_client():
    """Persistent client, created lazily so importing this package stays cheap."""
    global _client
    if _client is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
    return _client


def get_collection(name: str):
    """Fetch a collection, creating it if the ingest script has not run yet.

    Cosine distance is set explicitly because both models produce embeddings whose
    magnitude carries no meaning, only direction, and Chroma defaults to squared L2.
    """
    return get_chroma_client().get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(name: str):
    """Drop and recreate a collection so a re-ingest leaves no stale vectors."""
    client = get_chroma_client()
    try:
        client.delete_collection(name)
    except Exception:
        # Nothing to delete on the first run.
        pass
    return get_collection(name)
