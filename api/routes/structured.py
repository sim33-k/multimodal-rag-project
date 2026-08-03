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

CATEGORY_PLURALS = {
    "beach": "beaches",
    "mountain": "mountains",
    "national_park": "national parks",
    "historical_site": "historical sites",
}


def describe_filters(request: StructuredQueryRequest) -> str:
    """Phrase the active filters as a question, for when no keyword was typed.

    A structured search is often run entirely from the dropdowns, leaving the
    keyword box empty. Passing that empty string to the model produces a reply
    asking the user what they wanted to know, which reads like a broken page. So
    the filter set is turned back into a sentence and that is what gets answered.
    """
    subject = CATEGORY_PLURALS.get(request.category, "attractions")

    clauses = []
    if request.district:
        clauses.append(f"in the {request.district} district")
    if request.accessibility:
        clauses.append(f"that are {request.accessibility} to reach")
    if request.free_entry:
        clauses.append("with free entry")
    if request.unesco_only:
        clauses.append("that are UNESCO listed")

    return f"Tell me about {subject} in Sri Lanka {' '.join(clauses)}".strip()


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
        query=request.query.strip() or describe_filters(request),
        query_type="structured",
        rows=rows,
        retrievers_used=retrievers,
        generate=request.generate,
    )
