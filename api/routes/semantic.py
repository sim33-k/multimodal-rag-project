# Semantic queries - embedding search over the descriptions.

from fastapi import APIRouter

from api.routes import build_response
from api.schemas import QueryResponse, SemanticQueryRequest
from retrieval import semantic_search

router = APIRouter()


@router.post("/semantic", response_model=QueryResponse)
def semantic_query(request: SemanticQueryRequest) -> QueryResponse:
    rows = semantic_search.search(
        query=request.query,
        limit=request.limit,
        category=request.category,
        district=request.district,
    )

    return build_response(
        query=request.query,
        query_type="semantic",
        rows=rows,
        retrievers_used=["semantic"],
        generate=request.generate,
    )
