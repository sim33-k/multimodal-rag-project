"""Text embeddings for semantic search, using sentence-transformers MiniLM.

The document embedded per attraction is the hand-written description joined with
its name, category and district. Folding those structured fields into the text
means a query like "ancient city in Matale" can match on the district even though
the description never spells it out.

Run with:  python -m embeddings.text_embed
"""

import json
import sys

from sentence_transformers import SentenceTransformer

from db.connection import PROJECT_ROOT, fetch_all
from embeddings import TEXT_COLLECTION, get_collection, reset_collection

MODEL_NAME = "all-MiniLM-L6-v2"
DESCRIPTIONS_DIR = PROJECT_ROOT / "data" / "descriptions"

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Loaded once per process. The first call downloads ~90MB to the HF cache."""
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_query(query: str) -> list[float]:
    """Encode a user query into the same space as the stored descriptions."""
    return get_model().encode(query, normalize_embeddings=True).tolist()


def load_descriptions() -> dict[str, str]:
    """Read every descriptions JSON file into an {attraction_id: description} map."""
    descriptions: dict[str, str] = {}
    for path in sorted(DESCRIPTIONS_DIR.glob("*.json")):
        entries = json.loads(path.read_text(encoding="utf-8"))
        for entry in entries:
            descriptions[entry["id"]] = entry["description"]
    return descriptions


def build_document(row: dict, description: str) -> str:
    """Combine structured fields with the prose into one embeddable document."""
    parts = [
        f"{row['name']}.",
        f"Category: {row['category'].replace('_', ' ')}.",
        f"Located in {row['location']}, {row['district']} District, Sri Lanka."
        if row.get("location")
        else f"Located in {row['district']} District, Sri Lanka.",
        f"Best season: {row['best_season']}." if row.get("best_season") else "",
        f"Accessibility: {row['accessibility']}." if row.get("accessibility") else "",
        description,
    ]
    return " ".join(part for part in parts if part)


def main() -> None:
    descriptions = load_descriptions()
    if not descriptions:
        print("No description files found under data/descriptions/. Nothing to embed.")
        return

    rows = fetch_all(
        "SELECT id, name, category, location, district, best_season, accessibility "
        "FROM attractions ORDER BY id"
    )
    if not rows:
        print("No attractions in the database. Run `python -m db.init_db` first.")
        return

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    missing: list[str] = []

    for row in rows:
        description = descriptions.get(row["id"])
        if not description:
            missing.append(row["id"])
            continue
        ids.append(row["id"])
        documents.append(build_document(row, description))
        metadatas.append(
            {
                "name": row["name"],
                "category": row["category"],
                "district": row["district"] or "",
            }
        )

    print(f"Encoding {len(documents)} descriptions with {MODEL_NAME}...")
    vectors = get_model().encode(
        documents, normalize_embeddings=True, show_progress_bar=False
    )

    # Rebuilt from scratch each run so a re-import never leaves stale vectors behind.
    collection = reset_collection(TEXT_COLLECTION)

    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=[vector.tolist() for vector in vectors],
    )

    print(f"Stored {collection.count()} text embeddings in '{TEXT_COLLECTION}'.")
    if missing:
        print(f"No description written yet for: {', '.join(missing)}")


if __name__ == "__main__":
    sys.exit(main())
