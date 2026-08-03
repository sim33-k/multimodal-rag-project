# Image embeddings using CLIP.
#
# CLIP puts pictures and text in the same vector space, which is why the image
# tab can do both things: upload a photo and find similar photos, or type
# "golden sand" and match against the photos directly.
#
# Run:  python embeddings/image_embed.py

import sys
from pathlib import Path

# db and embeddings aren't installed as packages, so add the project root to
# the path by hand
sys.path.append(str(Path(__file__).resolve().parent.parent))

import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

from db.connection import PROJECT_ROOT, fetch_all
from embeddings import IMAGE_COLLECTION, reset_collection

MODEL_NAME = "openai/clip-vit-base-patch32"
BATCH_SIZE = 16

model = None
processor = None


def embed_images(images):
    global model, processor
    if model is None:
        # first run downloads about 600MB
        model = CLIPModel.from_pretrained(MODEL_NAME)
        model.eval()
        processor = CLIPProcessor.from_pretrained(MODEL_NAME)

    inputs = processor(images=images, return_tensors="pt")
    with torch.no_grad():
        output = model.get_image_features(**inputs)
        # transformers 4.x gives back a plain tensor here but 5.x gives an
        # object with the tensor in .pooler_output, so handle both
        if isinstance(output, torch.Tensor):
            features = output
        elif getattr(output, "pooler_output", None) is not None:
            features = output.pooler_output
        else:
            raise TypeError("Unexpected CLIP output: " + type(output).__name__)

    # make them unit length so cosine distance works properly
    features = features / features.norm(dim=-1, keepdim=True)
    return features.tolist()


def embed_image(image):
    return embed_images([image])[0]


def embed_text(text):
    # NOTE: this is CLIP's text encoder, not MiniLM. Different vector space,
    # never compare the two.
    global model, processor
    if model is None:
        model = CLIPModel.from_pretrained(MODEL_NAME)
        model.eval()
        processor = CLIPProcessor.from_pretrained(MODEL_NAME)

    inputs = processor(text=[text], return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        output = model.get_text_features(**inputs)
        if isinstance(output, torch.Tensor):
            features = output
        elif getattr(output, "pooler_output", None) is not None:
            features = output.pooler_output
        else:
            raise TypeError("Unexpected CLIP output: " + type(output).__name__)

    features = features / features.norm(dim=-1, keepdim=True)
    return features[0].tolist()


if __name__ == "__main__":
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
        print("No images in the database. Run python data/fetch_images.py then "
              "python db/init_db.py first.")
    else:
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
            # id is the image id not the attraction id, because one attraction
            # can have more than one photo. attraction_id goes in the metadata
            # so we can group them back together when searching.
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
        else:
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
