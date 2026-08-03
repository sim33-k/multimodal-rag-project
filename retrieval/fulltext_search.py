"""Lexical retrieval using Postgres full-text search.

This is the counterweight to the embedding-based search. Dense vectors are good
at paraphrase but blur proper nouns together, so a query naming "Yapahuwa" can
rank other rock fortresses above the one actually asked for. A tsvector match on
the exact lexeme does not have that failure mode, which is precisely why both
retrievers are fused rather than one being chosen.
"""

from db.connection import fetch_all
from retrieval.sql_query import attach_images, clean_row


def _search(query_function: str, query: str, limit: int) -> list[dict]:
    """Run a ranked tsquery match. query_function is a Postgres tsquery builder."""
    return fetch_all(
        f"""
        SELECT a.id, ts_rank(a.search_vector, {query_function}('english', :query)) AS rank
        FROM attractions a
        WHERE a.search_vector @@ {query_function}('english', :query)
        ORDER BY rank DESC
        LIMIT :limit
        """,
        {"query": query, "limit": limit},
    )


def search_ids(query: str, limit: int = 10) -> list[str]:
    """Ranked attraction ids for a keyword query, best match first.

    Two passes: websearch_to_tsquery requires every term to be present, which is
    precise but returns nothing for a conversational query like "old rock fortress
    near Matale". When that happens, fall back to an OR of the individual terms so
    partial matches still surface, and let the ranking sort out relevance.
    """
    query = (query or "").strip()
    if not query:
        return []

    rows = _search("websearch_to_tsquery", query, limit)

    if not rows:
        terms = [term for term in query.replace(",", " ").split() if len(term) > 2]
        if terms:
            rows = _search("to_tsquery", " | ".join(terms), limit)

    return [row["id"] for row in rows]


def search(query: str, limit: int = 10) -> list[dict]:
    """Full rows for a keyword query, in rank order."""
    ids = search_ids(query, limit)
    if not ids:
        return []

    rows = fetch_all(
        "SELECT * FROM attractions_full WHERE id = ANY(:ids)", {"ids": ids}
    )
    by_id = {row["id"]: clean_row(row) for row in rows}
    return attach_images([by_id[key] for key in ids if key in by_id])
