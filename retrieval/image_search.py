# Image search over the CLIP collection. Two ways in:
#   search_by_image - upload a photo, find similar looking places
#   search_by_text  - type a description, match against the photos
#
# The second one is not the same as semantic_search. That searches the written
# descriptions; this searches the actual pictures, so "golden sand and palm
# trees" can find a beach whose description never says those words.

from embeddings import IMAGE_COLLECTION, get_collection
from embeddings.image_embed import embed_image, embed_text
from retrieval.sql_query import get_by_ids


def collapse_to_attractions(results, limit):
    # An attraction can have 2 photos and we don't want it taking 2 of the top
    # slots, so keep only its best matching image.
    metadatas = results["metadatas"][0] if results.get("metadatas") else []
    distances = results["distances"][0] if results.get("distances") else []

    best = {}
    for metadata, distance in zip(metadatas, distances):
        attraction_id = metadata["attraction_id"]
        similarity = 1 - distance
        if attraction_id not in best or similarity > best[attraction_id]:
            best[attraction_id] = similarity

    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    return ranked[:limit]


def run_search(embedding, limit, category):
    collection = get_collection(IMAGE_COLLECTION)
    if collection.count() == 0:
        return []

    where = None
    if category:
        where = {"category": {"$eq": category}}

    # ask for more than we need since several images can collapse into the
    # same attraction
    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(limit * 3, collection.count()),
        where=where,
    )

    ranked = collapse_to_attractions(results, limit)
    rows = get_by_ids([attraction_id for attraction_id, score in ranked])

    scores = dict(ranked)
    for row in rows:
        row["similarity"] = round(scores.get(row["id"], 0.0), 4)
    return rows


def search_by_image(image, limit=10, category=None):
    return run_search(embed_image(image), limit, category)


def search_by_text(query, limit=10, category=None):
    if query is None:
        return []
    query = query.strip()
    if query == "":
        return []
    return run_search(embed_text(query), limit, category)


def search_ids_by_text(query, limit=10):
    return [row["id"] for row in search_by_text(query, limit)]
