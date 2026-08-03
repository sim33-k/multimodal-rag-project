"""Structured queries: filtered SQL, with full-text search folded in.

When the request carries free-text as well as filters, the SQL result is unioned
with a tsvector match so a named place is not missed just because it fell outside
the filter combination. Both are lexical, so no fusion is needed - the SQL result
leads and full-text tops it up.
"""

from fastapi import APIRouter

from api.routes import build_response
from api.schemas import QueryResponse, StructuredQueryRequest
from retrieval import fulltext_search, sql_query

router = APIRouter()


@router.post("/structured", response_model=QueryResponse)
def structured_query(request: StructuredQueryRequest) -> QueryResponse:
    """Filter attractions by category, district, accessibility, fee and UNESCO status."""
    rows = sql_query.structured_search(
        category=request.category,
        district=request.district,
        accessibility=request.accessibility,
        free_entry=request.free_entry,
        unesco_only=request.unesco_only,
        limit=request.limit,
    )
    retrievers = ["sql"]

    if request.query.strip():
        seen = {row["id"] for row in rows}
        extra = [
            row
            for row in fulltext_search.search(request.query, request.limit)
            if row["id"] not in seen
        ]
        if extra:
            rows.extend(extra)
            retrievers.append("fulltext")
        rows = rows[: request.limit]

    return build_response(
        query=request.query,
        query_type="structured",
        rows=rows,
        retrievers_used=retrievers,
        generate=request.generate,
    )
