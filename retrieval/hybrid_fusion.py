"""Reciprocal Rank Fusion for merging several ranked result lists.

    score(d) = sum over retrievers i of  1 / (k + rank_i(d)),  k = 60

The point of RRF is that it uses only the *position* of a document in each list,
never the score. That matters here because the retrievers produce numbers that
are not comparable: Postgres ts_rank is an unbounded relevance figure, MiniLM
cosine similarity sits in a narrow band around 0.3-0.7, and CLIP similarities sit
somewhere else again. Normalising those onto a shared scale would need tuning per
retriever and would drift as the data grows; ranks need none of that.

k = 60 is the value from the original Cormack et al. paper. It damps the gap
between the top few positions, so an item ranked 1st by one retriever and absent
from another does not automatically beat an item ranked 2nd and 3rd by both.
"""

RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: dict[str, list[str]], k: int = RRF_K, limit: int = 10
) -> list[dict]:
    """Merge {retriever name: [ids in rank order]} into one ranked list.

    Returns dicts of {id, score, sources, ranks} rather than bare ids, because the
    UI and the report both need to show *why* something was ranked where it was.
    """
    scores: dict[str, float] = {}
    sources: dict[str, list[str]] = {}
    ranks: dict[str, dict[str, int]] = {}

    for retriever, ids in ranked_lists.items():
        for position, attraction_id in enumerate(ids, start=1):
            scores[attraction_id] = scores.get(attraction_id, 0.0) + 1.0 / (k + position)
            sources.setdefault(attraction_id, []).append(retriever)
            ranks.setdefault(attraction_id, {})[retriever] = position

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    return [
        {
            "id": attraction_id,
            "score": round(score, 6),
            "sources": sources[attraction_id],
            "ranks": ranks[attraction_id],
        }
        for attraction_id, score in ordered[:limit]
    ]


def fuse_ids(ranked_lists: dict[str, list[str]], limit: int = 10) -> list[str]:
    """Convenience wrapper for callers that only want the merged id order."""
    return [entry["id"] for entry in reciprocal_rank_fusion(ranked_lists, limit=limit)]
