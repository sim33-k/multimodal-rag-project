# Reciprocal Rank Fusion - merges several ranked lists into one list.
#
#   score(d) = sum of  1 / (k + position of d in list i)     with k = 60
#
# It only looks at the position of a result in each list, never the score. Our
# scores are not comparable at all - ts_rank has no upper bound, MiniLM
# similarities sit around 0.3 to 0.7 and CLIP ones around 0.15 to 0.35 - so
# trying to combine the numbers directly would need tuning for each one.
# Positions need none of that.
#
# k = 60 is the value from the Cormack et al. paper.

RRF_K = 60


def reciprocal_rank_fusion(ranked_lists, k=RRF_K, limit=10):
    # ranked_lists looks like {"semantic": [id1, id2, ...], "fulltext": [...]}
    scores = {}
    sources = {}
    ranks = {}

    for retriever in ranked_lists:
        ids = ranked_lists[retriever]
        position = 1
        for attraction_id in ids:
            if attraction_id not in scores:
                scores[attraction_id] = 0.0
                sources[attraction_id] = []
                ranks[attraction_id] = {}

            scores[attraction_id] = scores[attraction_id] + 1.0 / (k + position)
            sources[attraction_id].append(retriever)
            ranks[attraction_id][retriever] = position
            position = position + 1

    # biggest score first
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    # we return the sources and positions too, not just the ids, so the page can
    # show which retrievers found each result
    out = []
    for pair in ordered[:limit]:
        attraction_id = pair[0]
        out.append({
            "id": attraction_id,
            "score": round(pair[1], 6),
            "sources": sources[attraction_id],
            "ranks": ranks[attraction_id],
        })
    return out


def fuse_ids(ranked_lists, limit=10):
    fused = reciprocal_rank_fusion(ranked_lists, limit=limit)
    ids = []
    for entry in fused:
        ids.append(entry["id"])
    return ids
