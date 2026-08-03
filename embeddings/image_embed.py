"""Image embeddings for visual search, using OpenAI CLIP ViT-B/32.

CLIP puts images and text into a single shared vector space. That is what makes
both halves of the image tab work: an uploaded photo is compared against stored
photos, and a text phrase like "ancient stone ruins" can also be matched directly
against images without any caption having been written.

Run with:  python -m embeddings.image_embed
"""

import sys

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from db.connection import PROJECT_ROOT, fetch_all
from embeddings import IMAGE_COLLECTION, reset_collection

MODEL_NAME = "openai/clip-vit-base-patch32"

_model: CLIPModel | None = None
_processor: CLIPProcessor | None = None


def get_model() -> tuple[CLIPModel, CLIPProcessor]:
    """Loaded once per process. The first call downloads ~600MB to the HF cache."""
    global _model, _processor
    if _model is None:
        _model = CLIPModel.from_pretrained(MODEL_NAME)
        _model.eval()
        _processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    return _model, _processor


def _as_tensor(output) -> torch.Tensor:
    """Pull the embedding tensor out of whatever get_*_features returned.

    transformers 4.x returns a bare tensor here; 5.x returns a ModelOutput whose
    pooler_output holds the projected embedding. Handling both keeps this working
    across the versions either team member might have installed.
    """
    if isinstance(output, torch.Tensor):
        return output
    if getattr(output, "pooler_output", None) is not None:
        return output.pooler_output
    raise TypeError(f"Unexpected CLIP output type: {type(output).__name__}")


def _normalise(features: torch.Tensor) -> torch.Tensor:
    """Unit-length rows, so cosine distance in Chroma behaves as expected."""
    return features / features.norm(dim=-1, keepdim=True)


def embed_images(images: list[Image.Image]) -> list[list[float]]:
    model, processor = get_model()
    inputs = processor(images=images, return_tensors="pt")
    with torch.no_grad():
        features = _as_tensor(model.get_image_features(**inputs))
    return _normalise(features).tolist()


def embed_image(image: Image.Image) -> list[float]:
    """Encode one uploaded image for a visual similarity query."""
    return embed_images([image])[0]


def embed_text(text: str) -> list[float]:
    """Encode a text phrase into CLIP's shared space, for text-to-image search.

    Note this is a different vector space from the MiniLM embeddings used for
    semantic description search - the two are never compared against each other.
    """
    model, processor = get_model()
    inputs = processor(text=[text], return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        features = _as_tensor(model.get_text_features(**inputs))
    return _normalise(features)[0].tolist()


def main() -> None:
    rows = fetch_all(
        """
        SELECT i.image_id, i.file_path, i.caption,
               a.id AS attraction_id, a.name, a.category, a.district
        FROM images i
        JOIN attractions a ON a.id = i.attraction_id
        ORDER BY i.image_id
        """
    )
    if not rows:
        print(
            "No images registered. Run `python -m data.fetch_images` then "
            "`python -m db.init_db` first."
        )
        return

    ids: list[str] = []
    metadatas: list[dict] = []
    loaded: list[Image.Image] = []
    missing: list[str] = []

    for row in rows:
        path = PROJECT_ROOT / row["file_path"]
        if not path.exists():
            missing.append(row["file_path"])
            continue
        loaded.append(Image.open(path).convert("RGB"))
        # The Chroma id is the image id, not the attraction id, because one
        # attraction can have several images. The attraction is carried in metadata
        # so results can be collapsed back per attraction at query time.
        ids.append(f"img_{row['image_id']}")
        metadatas.append(
            {
                "attraction_id": row["attraction_id"],
                "name": row["name"],
                "category": row["category"],
                "district": row["district"] or "",
                "file_path": row["file_path"],
                "caption": row["caption"] or "",
            }
        )

    if not loaded:
        print("No image files found on disk. Nothing to embed.")
        return

    print(f"Encoding {len(loaded)} images with {MODEL_NAME}...")

    # Batched so memory stays flat regardless of how many images are added later.
    vectors: list[list[float]] = []
    batch_size = 16
    for start in range(0, len(loaded), batch_size):
        vectors.extend(embed_images(loaded[start : start + batch_size]))
        print(f"  {min(start + batch_size, len(loaded))}/{len(loaded)}")

    collection = reset_collection(IMAGE_COLLECTION)
    collection.add(
        ids=ids,
        metadatas=metadatas,
        embeddings=vectors,
        documents=[m["name"] for m in metadatas],
    )

    print(f"Stored {collection.count()} image embeddings in '{IMAGE_COLLECTION}'.")
    if missing:
        print(f"Registered in the database but missing on disk: {', '.join(missing)}")


if __name__ == "__main__":
    sys.exit(main())
