# Keyword search using Postgres full text search.
#
# This is here to balance out the embedding search. Embeddings are good at
# meaning but they blur place names together - searching "Yapahuwa" with
# embeddings also brings back Hikkaduwa and Yala. A tsvector match doesn't have
# that problem, which is why we run both and fuse the results.

from db.connection import fetch_all
from retrieval.sql_query import attach_images, clean_row


def run_query(query_function, query, limit):
    return fetch_all(
        "SELECT a.id, ts_rank(a.search_vector, " + query_function +
        "('english', :query)) AS rank "
        "FROM attractions a "
        "WHERE a.search_vector @@ " + query_function + "('english', :query) "
        "ORDER BY rank DESC LIMIT :limit",
        {"query": query, "limit": limit},
    )


def search_ids(query, limit=10):
    if query is None:
        return []
    query = query.strip()
    if query == "":
        return []

    # websearch_to_tsquery needs every word to match, which is right for
    # something like "Sigiriya" but gives nothing for a sentence like
    # "old rock fortress near Matale". So if that finds nothing, retry with the
    # words OR'd together and let ts_rank sort them.
    rows = run_query("websearch_to_tsquery", query, limit)

    if not rows:
        terms = []
        for term in query.replace(",", " ").split():
            if len(term) > 2:
                terms.append(term)
        if terms:
            rows = run_query("to_tsquery", " | ".join(terms), limit)

    return [row["id"] for row in rows]


def search(query, limit=10):
    ids = search_ids(query, limit)
    if not ids:
        return []

    rows = fetch_all("SELECT * FROM attractions_full WHERE id = ANY(:ids)",
                     {"ids": ids})

    by_id = {}
    for row in rows:
        by_id[row["id"]] = clean_row(row)

    ordered = []
    for key in ids:
        if key in by_id:
            ordered.append(by_id[key])
    return attach_images(ordered)
