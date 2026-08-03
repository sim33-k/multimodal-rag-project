# Semantic search over the ChromaDB text collection.
# The query is encoded with the same MiniLM model that made the stored vectors,
# otherwise the distances wouldn't mean anything.

from embeddings import TEXT_COLLECTION, get_collection
from embeddings.text_embed import embed_query
from retrieval.sql_query import get_by_ids


def build_where(category, district):
    # chroma wants $and written out if there is more than one condition
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


def run_query(query, limit, category, district):
    collection = get_collection(TEXT_COLLECTION)
    if collection.count() == 0:
        return None

    how_many = limit
    if how_many > collection.count():
        how_many = collection.count()

    # the filters go to chroma instead of being applied afterwards, otherwise
    # asking for 5 results could give you 5 that all get thrown away
    return collection.query(
        query_embeddings=[embed_query(query)],
        n_results=how_many,
        where=build_where(category, district),
    )


def search_ids(query, limit=10, category=None, district=None):
    if query is None:
        return []
    query = query.strip()
    if query == "":
        return []

    results = run_query(query, limit, category, district)
    if results is None:
        return []
    if not results["ids"]:
        return []
    return results["ids"][0]


def search(query, limit=10, category=None, district=None):
    if query is None:
        return []
    query = query.strip()
    if query == "":
        return []

    results = run_query(query, limit, category, district)
    if results is None:
        return []

    ids = []
    if results["ids"]:
        ids = results["ids"][0]

    distances = []
    if results.get("distances"):
        distances = results["distances"][0]

    # chroma gives us a distance, we want a similarity
    scores = {}
    i = 0
    while i < len(ids):
        scores[ids[i]] = 1 - distances[i]
        i = i + 1

    rows = get_by_ids(ids)
    for row in rows:
        if row["id"] in scores:
            row["similarity"] = round(scores[row["id"]], 4)
        else:
            row["similarity"] = 0.0
    return rows
