# makes text embeddings for semantic search using MiniLM
import json
import sys
from pathlib import Path

# need this so db and embeddings can be imported
sys.path.append(str(Path(__file__).resolve().parent.parent))

from sentence_transformers import SentenceTransformer

from db.connection import PROJECT_ROOT, fetch_all
from embeddings import TEXT_COLLECTION, reset_collection

MODEL_NAME = "all-MiniLM-L6-v2"
DESCRIPTIONS_DIR = PROJECT_ROOT / "data" / "descriptions"

model = None


def embed_query(query):
    global model
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    return model.encode(query, normalize_embeddings=True).tolist()


def load_descriptions():
    descriptions = {}
    for path in sorted(DESCRIPTIONS_DIR.glob("*.json")):
        entries = json.loads(path.read_text(encoding="utf-8"))
        for entry in entries:
            descriptions[entry["id"]] = entry["description"]
    return descriptions


if __name__ == "__main__":
    # description JSONs are keyed by attraction id
    descriptions = load_descriptions()
    if not descriptions:
        print("No description files in data/descriptions/.")
    else:
        # pull the attractions to build documents for
        rows = fetch_all(
            "SELECT id, name, category, location, district, best_season, accessibility "
            "FROM attractions ORDER BY id"
        )
        if not rows:
            print("No attractions in the database. Run python db/init_db.py first.")
        else:
            ids = []
            documents = []
            metadatas = []
            missing = []

            # build one document per attraction
            for row in rows:
                description = descriptions.get(row["id"])
                if not description:
                    missing.append(row["id"])
                    continue

                # add name/category/location info before the description
                parts = [row["name"] + "."]
                parts.append("Category: " + row["category"].replace("_", " ") + ".")

                if row.get("location"):
                    parts.append("Located in " + row["location"] + ", " + row["district"] +
                                 " District, Sri Lanka.")
                else:
                    parts.append("Located in " + row["district"] + " District, Sri Lanka.")

                if row.get("best_season"):
                    parts.append("Best season: " + row["best_season"] + ".")
                if row.get("accessibility"):
                    parts.append("Accessibility: " + row["accessibility"] + ".")

                parts.append(description)
                document = " ".join(parts)

                ids.append(row["id"])
                documents.append(document)
                metadatas.append({
                    "name": row["name"],
                    "category": row["category"],
                    "district": row["district"] or "",
                })

            print("Encoding " + str(len(documents)) + " descriptions with " + MODEL_NAME + "...")

            if model is None:
                model = SentenceTransformer(MODEL_NAME)
            vectors = model.encode(documents, normalize_embeddings=True,
                                    show_progress_bar=False)

            # chroma wants plain lists, not numpy arrays
            embeddings = []
            for v in vectors:
                embeddings.append(v.tolist())

            # wipe and rebuild the collection from scratch each run
            collection = reset_collection(TEXT_COLLECTION)
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )

            print("Stored " + str(collection.count()) + " text embeddings.")
            if missing:
                print("No description written yet for: " + ", ".join(missing))
