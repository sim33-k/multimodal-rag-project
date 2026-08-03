"""Visual retrieval over the ChromaDB image collection.

Two entry points, both landing in the same CLIP vector space:
  - search_by_image: encode an uploaded photo, find visually similar attractions
  - search_by_text:  encode a phrase, find attractions that *look* like it

The second is genuinely different from semantic_search. That one matches against
written descriptions; this one matches against the pixels, so "golden sand and
palm trees" can retrieve a beach whose description never uses those words.
"""

from PIL import Image

from embeddings import IMAGE_COLLECTION, get_collection
from embeddings.image_embed import embed_image, embed_text
from retrieval.sql_query import get_by_ids


def _collapse_to_attractions(results: dict, limit: int) -> list[tuple[str, float]]:
    """Reduce image hits to unique attractions, keeping each one's best match.

    An attraction with two stored images could otherwise take two of the top
    slots, which is not useful when the caller wants a list of places.
    """
    metadatas = results["metadatas"][0] if results.get("metadatas") else []
    distances = results["distances"][0] if results.get("distances") else []

    best: dict[str, float] = {}
    for metadata, distance in zip(metadatas, distances):
        attraction_id = metadata["attraction_id"]
        similarity = 1 - distance
        if attraction_id not in best or similarity > best[attraction_id]:
            best[attraction_id] = similarity

    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    return ranked[:limit]


def _query(embedding: list[float], limit: int, category: str | None) -> list[dict]:
    collection = get_collection(IMAGE_COLLECTION)
    if collection.count() == 0:
        return []

    where = {"category": {"$eq": category}} if category else None
    results = collection.query(
        query_embeddings=[embedding],
        # Over-fetch, because several hits can collapse onto the same attraction.
        n_results=min(limit * 3, collection.count()),
        where=where,
    )

    ranked = _collapse_to_attractions(results, limit)
    rows = get_by_ids([attraction_id for attraction_id, _ in ranked])
    scores = dict(ranked)
    for row in rows:
        row["similarity"] = round(scores.get(row["id"], 0.0), 4)
    return rows


def search_by_image(
    image: Image.Image, limit: int = 10, category: str | None = None
) -> list[dict]:
    return _query(embed_image(image), limit, category)


def search_by_text(
    query: str, limit: int = 10, category: str | None = None
) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    return _query(embed_text(query), limit, category)


def search_ids_by_text(query: str, limit: int = 10) -> list[str]:
    """Id-only variant, used by hybrid fusion."""
    return [row["id"] for row in search_by_text(query, limit)]
