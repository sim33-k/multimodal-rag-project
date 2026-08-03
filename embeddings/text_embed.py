# Makes the text embeddings for semantic search using MiniLM.
#
# We don't embed the description on its own - we stick the name, category and
# district on the front of it first. Otherwise a search like "beaches in Matara"
# finds nothing, because the descriptions don't usually mention the district.
#
# Run:  python -m embeddings.text_embed

import json
import sys

from sentence_transformers import SentenceTransformer

from db.connection import PROJECT_ROOT, fetch_all
from embeddings import TEXT_COLLECTION, reset_collection

MODEL_NAME = "all-MiniLM-L6-v2"
DESCRIPTIONS_DIR = PROJECT_ROOT / "data" / "descriptions"

model = None


def get_model():
    # loaded once, first time downloads about 90MB
    global model
    if model is None:
        model = SentenceTransformer(MODEL_NAME)
    return model


def embed_query(query):
    return get_model().encode(query, normalize_embeddings=True).tolist()


def load_descriptions():
    descriptions = {}
    for path in sorted(DESCRIPTIONS_DIR.glob("*.json")):
        entries = json.loads(path.read_text(encoding="utf-8"))
        for entry in entries:
            descriptions[entry["id"]] = entry["description"]
    return descriptions


def build_document(row, description):
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
    return " ".join(parts)


def main():
    descriptions = load_descriptions()
    if not descriptions:
        print("No description files in data/descriptions/. Nothing to do.")
        return

    rows = fetch_all(
        "SELECT id, name, category, location, district, best_season, accessibility "
        "FROM attractions ORDER BY id"
    )
    if not rows:
        print("No attractions in the database. Run python -m db.init_db first.")
        return

    ids = []
    documents = []
    metadatas = []
    missing = []

    for row in rows:
        description = descriptions.get(row["id"])
        if not description:
            missing.append(row["id"])
            continue
        ids.append(row["id"])
        documents.append(build_document(row, description))
        metadatas.append({
            "name": row["name"],
            "category": row["category"],
            "district": row["district"] or "",
        })

    print("Encoding " + str(len(documents)) + " descriptions with " + MODEL_NAME + "...")
    vectors = get_model().encode(documents, normalize_embeddings=True,
                                 show_progress_bar=False)

    collection = reset_collection(TEXT_COLLECTION)
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=[v.tolist() for v in vectors],
    )

    print("Stored " + str(collection.count()) + " text embeddings.")
    if missing:
        print("No description written yet for: " + ", ".join(missing))


if __name__ == "__main__":
    sys.exit(main())
