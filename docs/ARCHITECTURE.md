# System architecture

## Overview

The system is split into four layers, each with a single responsibility and a
hard boundary between them.

```
┌──────────────────────────────────────────────────────────────┐
│  Browser frontend (web/)                                     │
│  Renders results. Holds no query logic. HTTP only.           │
└───────────────────────────┬──────────────────────────────────┘
                            │  JSON / multipart over HTTP
┌───────────────────────────▼──────────────────────────────────┐
│  FastAPI backend (api/)                                      │
│  Validates requests, picks retrievers, assembles responses.  │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  Retrieval (retrieval/)          LLM (llm/)                  │
│  router, sql, fulltext,          context builder,            │
│  semantic, image, fusion         answer generation           │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│  Storage                                                     │
│  PostgreSQL 16 (Docker)        ChromaDB (local persistence)  │
│  structured + full-text        text + image vectors          │
└──────────────────────────────────────────────────────────────┘
```

## Why the frontend goes through an API

The frontend is served by the API but still goes through HTTP rather than being
wired into `retrieval/` directly, for three reasons:

1. **The retrieval pipeline stays demonstrable on its own.** FastAPI generates
   Swagger docs at `/docs`, so every query type can be exercised and shown without
   the UI existing at all.
2. **The UI cannot accidentally become the place logic lives.** With a process
   boundary in between, there is nowhere to put a "quick fix" that bypasses the
   retrieval layer.
3. **Parallel development.** The two halves were built against a fixed contract
   (`api/schemas.py`) rather than against each other's internals.

The cost is one HTTP round trip per query, which is negligible next to embedding
and LLM latency.

## Request flow

Taking the hybrid endpoint, which exercises everything:

1. **Route.** `retrieval/router.py` sends the query to Gemini with a JSON response
   schema, asking for an intent classification and any filters it can extract.
   The response is parsed, not pattern-matched.
2. **Reconcile filters.** Explicit UI filters override anything the router
   inferred — a category picked in the sidebar is a stronger signal than the
   model's reading of the sentence.
3. **Retrieve.** Whichever retrievers the route implies run and return ranked id
   lists. Each over-fetches (2× the requested limit) so fusion has enough overlap
   to work with.
4. **Constrain.** The structured SQL result is applied as a *set intersection*
   over those ranked lists, not as another list to fuse. See
   [structured retrieval is a filter](#structured-retrieval-is-a-filter-not-a-ranking).
5. **Fuse.** `hybrid_fusion.py` merges the ranked lists with Reciprocal Rank
   Fusion. When only one retriever ran there is nothing to fuse and its order is
   used as-is.
6. **Hydrate.** Fused ids are turned back into full rows from `attractions_full`,
   with images attached in a single batched query.
7. **Build context.** `llm/context_builder.py` renders the top rows as a numbered
   block, capped at 8 items.
8. **Generate.** `llm/generate.py` prompts Gemini to answer using only that
   context, and to say so when the context does not cover the question.

The response carries the answer, the rows, the context string and the list of
retrievers that ran — so the UI can show the evidence, not just the conclusion.

## Why Reciprocal Rank Fusion

The four retrievers produce scores that are not comparable:

| Retriever | Score | Range |
|---|---|---|
| Full-text | `ts_rank` | unbounded, corpus-dependent |
| Semantic | cosine similarity (MiniLM) | in practice ~0.2–0.7 |
| Image | cosine similarity (CLIP) | in practice ~0.15–0.35 |
| Structured | none — SQL either matches or does not | n/a |

Normalising these onto a shared scale would need per-retriever tuning, and the
calibration would drift as data is added. RRF sidesteps the problem by using only
each document's **position** in each list:

```
score(d) = Σ  1 / (k + rank_i(d))       k = 60
```

`k = 60` is the value from the original Cormack et al. paper. It damps the gap
between the top few positions, so a document ranked 1st by one retriever and
absent from the others does not automatically outrank one ranked 2nd and 3rd by
two retrievers. Agreement across retrievers is rewarded over dominance in one.

This is visible in the worked example in [EVALUATION.md](EVALUATION.md).

## Structured retrieval is a filter, not a ranking

The structured retriever is deliberately **not** one of the lists fed into RRF.

SQL returns a set. Ours comes back `ORDER BY name`, which is an alphabetical
ordering, and RRF has no way to distinguish that from a relevance ordering — it
would award whichever attraction sorts first the largest possible contribution,
`1/(60+1)`, purely for its initial letter. That is not a hypothetical: it produced
a measurably wrong ranking, documented in
[EVALUATION.md §2](EVALUATION.md#2-a-sql-filter-is-a-set-not-a-ranking).

So structured retrieval instead constrains which candidates are eligible:

```python
allowed_ids = {row["id"] for row in structured_rows}
ranked_lists = {name: [i for i in ids if i in allowed_ids]
                for name, ids in ranked_lists.items()}
```

Two details matter. It runs **after** every retriever, so the constraint applies
to the image retriever too — otherwise a beach could surface under a
`historical_site` query on visual similarity alone. And if the intersection comes
back empty the constraint is dropped entirely, so a router that misreads a
district degrades the results rather than blanking the page.

The general principle: RRF fuses *rankings*. A retriever that does not produce a
genuine relevance ordering belongs in the filter step, not the fusion step.

## Graceful degradation

Two external dependencies can fail: the Gemini API and the ChromaDB collections.
Neither takes the system down.

| Failure | Behaviour |
|---|---|
| No Gemini key, or quota exhausted | Router falls back to a keyword heuristic; answers are composed from the retrieved rows and labelled as such in the UI |
| Text collection empty | Semantic search returns nothing; SQL and full-text still work |
| Image collection empty | Image search returns nothing; other modes unaffected |
| Database unreachable | `/health` reports `degraded` and the frontend says so instead of showing an empty result |

The design rule is that a failure in the generation layer must never prevent
retrieval from being demonstrated. This matters in practice — a rate-limited API
key during a live demo should degrade the answer quality, not produce an error
page.

## Module boundaries

- `db/` owns the connection and the schema. Nothing else builds SQL connections.
- `retrieval/` returns plain dicts, never ORM objects, so results from different
  retrievers can be merged without type juggling.
- `llm/` receives already-retrieved rows. It never queries anything itself.
- `api/routes/` contains only each endpoint's retrieval strategy; the shared
  response assembly lives in `api/routes/__init__.py`.
- `web/` reads no files and opens no database connections.
