# hybrid queries route the question run whichever retrievers make sense then merge the ranked lists with RRF

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
    route = query_router.route_query(request.query)

    # use whatever the user picked in the UI over whatever the router guessed from the sentence
    category = request.category or route.get("category")
    district = request.district or route.get("district")
    accessibility = request.accessibility or route.get("accessibility")

    # grab more than we need from each retriever since fusion works much better with some overlap
    fetch_limit = max(request.limit * 2, 10)
    ranked_lists = {}

    semantic_ids = semantic_search.search_ids(request.query, limit=fetch_limit, category=category, district=district)
    if semantic_ids:
        ranked_lists["semantic"] = semantic_ids

    fulltext_ids = fulltext_search.search_ids(request.query, limit=fetch_limit)
    if fulltext_ids:
        ranked_lists["fulltext"] = fulltext_ids

    # only bother with image search if the router thought appearance mattered otherwise it just adds noise
    if route.get("query_type") in ["image", "hybrid"]:
        image_ids = image_search.search_ids_by_text(request.query, limit=fetch_limit)
        if image_ids:
            ranked_lists["image"] = image_ids

    # SQL results are used as a filter not another list to fuse since SQL comes back sorted by name and RRF would just reward whatever starts with an A
    has_filters = bool(category or district or accessibility or route.get("free_entry") or route.get("unesco_only"))
    structured_rows = sql_query.structured_search(category=category, district=district, accessibility=accessibility, free_entry=route.get("free_entry", False), unesco_only=route.get("unesco_only", False), limit=100)

    allowed_ids = None
    if has_filters:
        allowed_ids = set()
        for row in structured_rows:
            allowed_ids.add(row["id"])

    if allowed_ids is not None:
        filtered = {}
        for name in ranked_lists:
            kept = []
            for key in ranked_lists[name]:
                if key in allowed_ids:
                    kept.append(key)
            filtered[name] = kept

        # only apply it if something survives so a router that guessed the wrong district doesnt empty the whole page
        anything_left = False
        for name in filtered:
            if filtered[name]:
                anything_left = True
                break

        if anything_left:
            trimmed = {}
            for name in filtered:
                if filtered[name]:
                    trimmed[name] = filtered[name]
            ranked_lists = trimmed
        else:
            allowed_ids = None

    if not ranked_lists:
        # nothing ranked anything so fall back to the structured rows or just a general listing
        rows = structured_rows
        if not rows:
            rows = sql_query.structured_search(limit=request.limit)
        used = []
        if structured_rows:
            used = ["structured"]
        return build_response(query=request.query, query_type="hybrid", rows=rows[:request.limit], retrievers_used=used, route=route, generate=request.generate)

    fused = hybrid_fusion.reciprocal_rank_fusion(ranked_lists, limit=request.limit)
    fused_ids = []
    for entry in fused:
        fused_ids.append(entry["id"])
    rows = sql_query.get_by_ids(fused_ids)

    # put the fusion info on the rows so the UI can show which retrievers found each result
    scores = {}
    for entry in fused:
        scores[entry["id"]] = entry

    for row in rows:
        entry = scores.get(row["id"], {})
        row["fusion_score"] = entry.get("score")
        row["retrievers"] = entry.get("sources")

    retrievers_used = list(ranked_lists.keys())
    if allowed_ids is not None:
        retrievers_used.append("structured (filter)")

    return build_response(query=request.query, query_type="hybrid", rows=rows, retrievers_used=retrievers_used, route=route, generate=request.generate)
