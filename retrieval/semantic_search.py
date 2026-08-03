"""Semantic retrieval over the ChromaDB text collection.

Queries are encoded with the same MiniLM model that produced the stored document
vectors, so distances are meaningful. Structured filters are pushed down into
Chroma's metadata `where` clause rather than applied afterwards, otherwise a
top-k of 5 could return five results that the filter then removes entirely.
"""

from embeddings import TEXT_COLLECTION, get_collection
from embeddings.text_embed import embed_query
from retrieval.sql_query import get_by_ids


def _where_clause(category: str | None, district: str | None) -> dict | None:
    """Build Chroma's metadata filter. It needs $and explicitly for 2+ conditions."""
    conditions = []
    if category:
        conditions.append({"category": {"$eq": category}})
    if district:
        conditions.append({"district": {"$eq": district}})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def search_ids(
    query: str,
    limit: int = 10,
    category: str | None = None,
    district: str | None = None,
) -> list[str]:
    """Ranked attraction ids for a natural-language query, closest first."""
    query = (query or "").strip()
    if not query:
        return []

    collection = get_collection(TEXT_COLLECTION)
    if collection.count() == 0:
        return []

    results = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=min(limit, collection.count()),
        where=_where_clause(category, district),
    )
    return results["ids"][0] if results["ids"] else []


def search(
    query: str,
    limit: int = 10,
    category: str | None = None,
    district: str | None = None,
) -> list[dict]:
    """Full rows for a natural-language query, in similarity order.

    Chroma returns cosine distance, so similarity is 1 - distance. It is carried
    through on the row because the UI shows it and the report uses it as evidence
    that retrieval is doing real work.
    """
    query = (query or "").strip()
    if not query:
        return []

    collection = get_collection(TEXT_COLLECTION)
    if collection.count() == 0:
        return []

    results = collection.query(
        query_embeddings=[embed_query(query)],
        n_results=min(limit, collection.count()),
        where=_where_clause(category, district),
    )

    ids = results["ids"][0] if results["ids"] else []
    distances = results["distances"][0] if results.get("distances") else []

    rows = get_by_ids(ids)
    scores = {key: 1 - distance for key, distance in zip(ids, distances)}
    for row in rows:
        row["similarity"] = round(scores.get(row["id"], 0.0), 4)
    return rows
