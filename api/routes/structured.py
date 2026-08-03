# Structured queries - SQL filters, plus full text search if a keyword is given.

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


def describe_filters(request):
    # People usually search this tab with the dropdowns and leave the keyword
    # box empty. Sending an empty query to Gemini makes it reply asking what you
    # wanted to know, which looks broken, so turn the filters into a sentence
    # and let it answer that instead.
    subject = CATEGORY_PLURALS.get(request.category, "attractions")

    clauses = []
    if request.district:
        clauses.append("in the " + request.district + " district")
    if request.accessibility:
        clauses.append("that are " + request.accessibility + " to reach")
    if request.free_entry:
        clauses.append("with free entry")
    if request.unesco_only:
        clauses.append("that are UNESCO listed")

    return ("Tell me about " + subject + " in Sri Lanka " + " ".join(clauses)).strip()


@router.post("/structured", response_model=QueryResponse)
def structured_query(request: StructuredQueryRequest) -> QueryResponse:
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
        # top up the filtered list with keyword matches, so a named place isn't
        # missed just because it fell outside the filters
        seen = set()
        for row in rows:
            seen.add(row["id"])

        extra = []
        for row in fulltext_search.search(request.query, request.limit):
            if row["id"] not in seen:
                extra.append(row)

        if extra:
            rows.extend(extra)
            retrievers.append("fulltext")
        rows = rows[:request.limit]

    query = request.query.strip()
    if not query:
        query = describe_filters(request)

    return build_response(
        query=query,
        query_type="structured",
        rows=rows,
        retrievers_used=retrievers,
        generate=request.generate,
    )
