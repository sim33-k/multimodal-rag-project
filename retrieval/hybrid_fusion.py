# Reciprocal Rank Fusion - merges several ranked lists into one.
#
#   score(d) = sum of  1 / (k + rank of d in list i)     with k = 60
#
# It only looks at the position of a result in each list, not its score. That
# matters because our scores aren't comparable at all: ts_rank is unbounded,
# MiniLM similarities sit around 0.3-0.7 and CLIP ones around 0.15-0.35. Ranks
# need no tuning.
#
# k=60 is the number from the Cormack et al. paper.

RRF_K = 60


def reciprocal_rank_fusion(ranked_lists, k=RRF_K, limit=10):
    # ranked_lists is {retriever name: [ids in order]}
    scores = {}
    sources = {}
    ranks = {}

    for retriever in ranked_lists:
        position = 1
        for attraction_id in ranked_lists[retriever]:
            if attraction_id not in scores:
                scores[attraction_id] = 0.0
                sources[attraction_id] = []
                ranks[attraction_id] = {}
            scores[attraction_id] += 1.0 / (k + position)
            sources[attraction_id].append(retriever)
            ranks[attraction_id][retriever] = position
            position += 1

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    # returning the sources and ranks too, not just the ids, so the UI can show
    # why something ended up where it did
    out = []
    for attraction_id, score in ordered[:limit]:
        out.append({
            "id": attraction_id,
            "score": round(score, 6),
            "sources": sources[attraction_id],
            "ranks": ranks[attraction_id],
        })
    return out


def fuse_ids(ranked_lists, limit=10):
    return [entry["id"] for entry in reciprocal_rank_fusion(ranked_lists, limit=limit)]
