# Image search over the CLIP collection. Two ways in:
#   search_by_image - upload a photo, find similar looking places
#   search_by_text  - type a description, match against the photos
#
# The second one is not the same as semantic_search. That one searches the
# written descriptions, this one searches the actual pictures, so
# "golden sand and palm trees" can find a beach whose description never says
# those words.

from embeddings import IMAGE_COLLECTION, get_collection
from embeddings.image_embed import embed_image, embed_text
from retrieval.sql_query import get_by_ids


def collapse_to_attractions(results, limit):
    # An attraction can have 2 photos and we don't want it taking up 2 of the
    # top slots, so just keep the best score for each one.
    metadatas = []
    if results.get("metadatas"):
        metadatas = results["metadatas"][0]

    distances = []
    if results.get("distances"):
        distances = results["distances"][0]

    best = {}
    i = 0
    while i < len(metadatas):
        attraction_id = metadatas[i]["attraction_id"]
        similarity = 1 - distances[i]
        if attraction_id not in best:
            best[attraction_id] = similarity
        else:
            if similarity > best[attraction_id]:
                best[attraction_id] = similarity
        i = i + 1

    # highest similarity first
    ranked = sorted(best.items(), key=lambda item: item[1], reverse=True)
    return ranked[:limit]


def run_search(embedding, limit, category):
    collection = get_collection(IMAGE_COLLECTION)
    if collection.count() == 0:
        return []

    where = None
    if category:
        where = {"category": {"$eq": category}}

    # ask for 3x what we need because a few of the images will belong to the
    # same attraction and get merged together
    how_many = limit * 3
    if how_many > collection.count():
        how_many = collection.count()

    results = collection.query(
        query_embeddings=[embedding],
        n_results=how_many,
        where=where,
    )

    ranked = collapse_to_attractions(results, limit)

    ids = []
    for pair in ranked:
        ids.append(pair[0])

    scores = {}
    for pair in ranked:
        scores[pair[0]] = pair[1]

    rows = get_by_ids(ids)
    for row in rows:
        if row["id"] in scores:
            row["similarity"] = round(scores[row["id"]], 4)
        else:
            row["similarity"] = 0.0
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
    rows = search_by_text(query, limit)
    ids = []
    for row in rows:
        ids.append(row["id"])
    return ids
