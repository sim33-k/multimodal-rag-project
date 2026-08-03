# ChromaDB setup. Both embedding scripts need the same client pointing at the
# same folder, so it gets made here instead of in each of them.

from pathlib import Path

import chromadb
from chromadb.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHROMA_PATH = PROJECT_ROOT / "embeddings" / "chroma_store"

TEXT_COLLECTION = "text_descriptions"
IMAGE_COLLECTION = "image_embeddings"

client = None


def get_chroma_client():
    global client
    if client is None:
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(CHROMA_PATH),
            settings=Settings(anonymized_telemetry=False),
        )
    return client


def get_collection(name):
    # cosine, not the default L2. our vectors are all normalised so only the
    # direction means anything
    c = get_chroma_client()
    return c.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def reset_collection(name):
    # delete then recreate, otherwise the old vectors are still in there after
    # a re-import
    c = get_chroma_client()
    try:
        c.delete_collection(name)
    except Exception:
        # first run, there is nothing to delete
        pass
    return get_collection(name)
