# makes image embeddings using CLIP
import sys
from pathlib import Path

# need this so db and embeddings can be imported
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
        model = CLIPModel.from_pretrained(MODEL_NAME)
        model.eval()
        processor = CLIPProcessor.from_pretrained(MODEL_NAME)

    inputs = processor(images=images,return_tensors="pt")
    with torch.no_grad():
        output = model.get_image_features(**inputs)
        # different transformers versions return this differently
        if isinstance(output, torch.Tensor):
            features = output
        elif getattr(output, "pooler_output", None) is not None:
            features = output.pooler_output
        else:
            raise TypeError("Unexpected CLIP output: " + type(output).__name__)

    # make them unit length so cosine distance works properly
    features = features / features.norm(dim=-1,keepdim=True)
    return features.tolist()


def embed_image(image):
    return embed_images([image])[0]


def embed_text(text):
    # this is CLIP's text encoder, not MiniLM. So we get a verry different vector space... cannot compare the two
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
    # pull every image row along with its attraction info
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
        print("No images in the database. Run python db/init_db.py first.")
    else:
        ids = []
        metadatas = []
        loaded = []
        missing = []

        # open each image file and build its metadata
        for row in rows:
            path = PROJECT_ROOT / row["file_path"]
            if not path.exists():
                missing.append(row["file_path"])
                continue
            loaded.append(Image.open(path).convert("RGB"))
            # this is the image id, not the attraction id
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
            print("No image files found on DRIVE!!.")
        else:
            print("Encoding " + str(len(loaded)) + " images with " + MODEL_NAME + "...")


            # we are going to do it in small small batch... or else this will take so much memory
            vectors = []
            start = 0
            while start < len(loaded):
                batch = loaded[start:start + BATCH_SIZE]
                vectors.extend(embed_images(batch))
                start = start + BATCH_SIZE
                print("  " + str(min(start, len(loaded))) + "/" + str(len(loaded)))

            documents = []
            for m in metadatas:
                documents.append(m["name"])

            # store into chroma
            collection = reset_collection(IMAGE_COLLECTION)
            collection.add(
                ids=ids,
                metadatas=metadatas,
                embeddings=vectors,
                documents=documents,
            )

            print("Stored " + str(collection.count()) + " image embeddings.")
            if missing:
                print("it is in database but missing in the drive??: " + ", ".join(missing))
