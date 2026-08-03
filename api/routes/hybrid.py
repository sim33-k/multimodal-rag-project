"""Hybrid queries: route with Gemini, run several retrievers, fuse with RRF.

This is the endpoint the router actually drives. It asks the router what the
query is, runs whichever retrievers that answer implies, and merges the ranked
lists with Reciprocal Rank Fusion. When only one retriever runs there is nothing
to fuse and its order is used directly.
"""

from fastapi import APIRouter

from api.routes import build_response
from api.schemas import HybridQueryRequest, QueryResponse
from retrieval import (
    fulltext_search,
    hybrid_fusion,
    image_search,
    router as query_router,
    semantic_search,
    sql_query,
)

router = APIRouter()


@router.post("/hybrid", response_model=QueryResponse)
def hybrid_query(request: HybridQueryRequest) -> QueryResponse:
    """Classify the query, run the relevant retrievers, and fuse their rankings."""
    route = query_router.route_query(request.query)

    # Explicit UI filters win over anything the router inferred: if the user
    # picked a category in the sidebar, that is a stronger signal than the LLM's
    # reading of the sentence.
    category = request.category or route.get("category")
    district = request.district or route.get("district")
    accessibility = request.accessibility or route.get("accessibility")

    # Over-fetch per retriever so fusion has enough overlap to work with. Fusing
    # two lists of 10 when only the top 5 are wanted gives a far better merged
    # ordering than fusing two lists of 5.
    fetch_limit = max(request.limit * 2, 10)
    ranked_lists: dict[str, list[str]] = {}

    semantic_ids = semantic_search.search_ids(
        request.query, limit=fetch_limit, category=category, district=district
    )
    if semantic_ids:
        ranked_lists["semantic"] = semantic_ids

    fulltext_ids = fulltext_search.search_ids(request.query, limit=fetch_limit)
    if fulltext_ids:
        ranked_lists["fulltext"] = fulltext_ids

    # Visual matching only contributes when the router judged appearance relevant,
    # since a CLIP text match on an unrelated query adds noise to the fusion.
    if route.get("query_type") in {"image", "hybrid"}:
        image_ids = image_search.search_ids_by_text(request.query, limit=fetch_limit)
        if image_ids:
            ranked_lists["image"] = image_ids

    # The structured retriever is applied as a *filter*, not as another ranked
    # list. SQL returns a set with no intrinsic relevance order - ours comes back
    # sorted by name - and feeding an alphabetical order into RRF actively
    # corrupts the fusion, because whichever attraction happens to sort first
    # collects the largest possible reciprocal-rank contribution. Intersecting
    # instead lets the filter constrain what is eligible while leaving the
    # ranking to the retrievers that actually produce one.
    #
    # This runs after every retriever, so the constraint applies to all of them.
    has_filters = bool(category or district or accessibility
                       or route.get("free_entry") or route.get("unesco_only"))
    structured_rows = sql_query.structured_search(
        category=category,
        district=district,
        accessibility=accessibility,
        free_entry=route.get("free_entry", False),
        unesco_only=route.get("unesco_only", False),
        limit=100,
    )
    allowed_ids = {row["id"] for row in structured_rows} if has_filters else None

    if allowed_ids is not None:
        filtered = {
            name: [key for key in ids if key in allowed_ids]
            for name, ids in ranked_lists.items()
        }
        # Only apply the constraint if it leaves something behind. A router that
        # inferred the wrong district should not empty the result set.
        if any(filtered.values()):
            ranked_lists = {name: ids for name, ids in filtered.items() if ids}
        else:
            allowed_ids = None

    if not ranked_lists:
        # No retriever produced a ranking. If filters were given, their result set
        # is still a perfectly good answer - this is the pure-filter case, e.g.
        # "beaches in Galle". Otherwise fall back to a general listing rather than
        # showing an empty page.
        rows = (structured_rows or sql_query.structured_search(limit=request.limit))
        return build_response(
            query=request.query,
            query_type="hybrid",
            rows=rows[: request.limit],
            retrievers_used=["structured"] if structured_rows else [],
            route=route,
            generate=request.generate,
        )

    fused = hybrid_fusion.reciprocal_rank_fusion(ranked_lists, limit=request.limit)
    rows = sql_query.get_by_ids([entry["id"] for entry in fused])

    # Carry the fusion evidence onto each row so the UI can show which retrievers
    # contributed to a result and at what rank.
    scores = {entry["id"]: entry for entry in fused}
    for row in rows:
        entry = scores.get(row["id"], {})
        row["fusion_score"] = entry.get("score")
        row["retrievers"] = entry.get("sources")

    retrievers_used = list(ranked_lists.keys())
    if allowed_ids is not None:
        retrievers_used.append("structured (filter)")

    return build_response(
        query=request.query,
        query_type="hybrid",
        rows=rows,
        retrievers_used=retrievers_used,
        route=route,
        generate=request.generate,
    )
