# Semantic search over the ChromaDB text collection.
# The query goes through the same MiniLM model that made the stored vectors,
# otherwise the distances would be meaningless.

from embeddings import TEXT_COLLECTION, get_collection
from embeddings.text_embed import embed_query
from retrieval.sql_query import get_by_ids


def build_where(category, district):
    # chroma needs $and spelled out if there's more than one condition
    conditions = []
    if category:
        conditions.append({"category": {"$eq": category}})
    if district:
        conditions.append({"district": {"$eq": district}})

    if len(conditions) == 0:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def search_ids(query, limit=10, category=None, district=None):
    if query is None:
        return []
    query = query.strip()
    if query == "":
        return []

    collection = get_collection(TEXT_COLLECTION)
    if collection.count() == 0:
        return []

    results = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=min(limit, collection.count()),
        where=build_where(category, district),
    )
    if not results["ids"]:
        return []
    return results["ids"][0]


def search(query, limit=10, category=None, district=None):
    if query is None:
        return []
    query = query.strip()
    if query == "":
        return []

    collection = get_collection(TEXT_COLLECTION)
    if collection.count() == 0:
        return []

    # the filters are passed to chroma rather than applied after, otherwise
    # asking for 5 results could give you 5 that all get filtered out
    results = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=min(limit, collection.count()),
        where=build_where(category, district),
    )

    ids = results["ids"][0] if results["ids"] else []
    distances = results["distances"][0] if results.get("distances") else []

    rows = get_by_ids(ids)

    # chroma gives distance, we want similarity
    scores = {}
    for key, distance in zip(ids, distances):
        scores[key] = 1 - distance

    for row in rows:
        row["similarity"] = round(scores.get(row["id"], 0.0), 4)
    return rows
