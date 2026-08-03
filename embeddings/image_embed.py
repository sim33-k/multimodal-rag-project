# Image embeddings using CLIP.
#
# CLIP puts pictures and text in the same vector space, which is why the image
# tab can do both things: upload a photo and find similar photos, or type
# "golden sand" and match against the photos directly.
#
# Run:  python -m embeddings.image_embed

import sys

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from db.connection import PROJECT_ROOT, fetch_all
from embeddings import IMAGE_COLLECTION, reset_collection

MODEL_NAME = "openai/clip-vit-base-patch32"
BATCH_SIZE = 16

model = None
processor = None


def get_model():
    # first run downloads about 600MB
    global model, processor
    if model is None:
        model = CLIPModel.from_pretrained(MODEL_NAME)
        model.eval()
        processor = CLIPProcessor.from_pretrained(MODEL_NAME)
    return model, processor


def as_tensor(output):
    # transformers 4.x gives back a plain tensor here but 5.x gives an object
    # with the tensor in .pooler_output, so handle both
    if isinstance(output, torch.Tensor):
        return output
    if getattr(output, "pooler_output", None) is not None:
        return output.pooler_output
    raise TypeError("Unexpected CLIP output: " + type(output).__name__)


def normalise(features):
    # make them unit length so cosine distance works properly
    return features / features.norm(dim=-1, keepdim=True)


def embed_images(images):
    m, p = get_model()
    inputs = p(images=images, return_tensors="pt")
    with torch.no_grad():
        features = as_tensor(m.get_image_features(**inputs))
    return normalise(features).tolist()


def embed_image(image):
    return embed_images([image])[0]


def embed_text(text):
    # NOTE: this is CLIP's text encoder, not MiniLM. Different vector space,
    # never compare the two.
    m, p = get_model()
    inputs = p(text=[text], return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        features = as_tensor(m.get_text_features(**inputs))
    return normalise(features)[0].tolist()


def main():
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
        print("No images in the database. Run python -m data.fetch_images then "
              "python -m db.init_db first.")
        return

    ids = []
    metadatas = []
    loaded = []
    missing = []

    for row in rows:
        path = PROJECT_ROOT / row["file_path"]
        if not path.exists():
            missing.append(row["file_path"])
            continue
        loaded.append(Image.open(path).convert("RGB"))
        # id is the image id not the attraction id, because one attraction can
        # have more than one photo. attraction_id goes in the metadata so we can
        # group them back together when searching.
        ids.append("img_" + str(row["image_id"]))
        metadatas.append({
            "attraction_id": row["attraction_id"],
            "name": row["name"],
            "category": row["category"],
            "district": row["district"] or "",
            "file_path": row["file_path"],
            "caption": row["caption"] or "",
        })

    if not loaded:
        print("No image files found on disk.")
        return

    print("Encoding " + str(len(loaded)) + " images with " + MODEL_NAME + "...")

    vectors = []
    start = 0
    while start < len(loaded):
        batch = loaded[start:start + BATCH_SIZE]
        vectors.extend(embed_images(batch))
        start = start + BATCH_SIZE
        print("  " + str(min(start, len(loaded))) + "/" + str(len(loaded)))

    collection = reset_collection(IMAGE_COLLECTION)
    collection.add(
        ids=ids,
        metadatas=metadatas,
        embeddings=vectors,
        documents=[m["name"] for m in metadatas],
    )

    print("Stored " + str(collection.count()) + " image embeddings.")
    if missing:
        print("In the database but missing on disk: " + ", ".join(missing))


if __name__ == "__main__":
    sys.exit(main())
