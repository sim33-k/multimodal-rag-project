# reciprocal rank fusion merges several ranked lists into one using just position not the raw scores since those arent comparable across retrievers
# k = 60 is the value used

RRF_K = 60


def score_of(item):
    return item[1]


def reciprocal_rank_fusion(ranked_lists, k=RRF_K, limit=10):
    # ranked_lists looks something like semantic goes to a list of ids and fulltext goes to another list of ids
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
    ordered = sorted(scores.items(), key=score_of, reverse=True)

    # sending back sources and positions too so the page can show which retriever found what
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
