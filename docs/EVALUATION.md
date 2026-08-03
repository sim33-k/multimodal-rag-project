# Evaluation

Observations recorded while developing against the 40-attraction dataset. All
figures below are from actual runs, not estimates. Reproduce any of them with
`generate: false` to skip the LLM call and see raw retrieval output.

---

## 1. The retrievers fail in different places

This is the central claim behind fusing them, so it is worth showing directly
rather than asserting. Three queries, run against full-text and semantic search
independently:

### 1a. Exact proper noun — `"Yapahuwa"`

| Retriever | Top 3 |
|---|---|
| Full-text | `yapahuwa` |
| Semantic | `yapahuwa`, `hikkaduwa_beach`, `yala_national_park` |

Both find it, but note what semantic search puts *behind* it: Hikkaduwa and Yala,
two places with no relationship to Yapahuwa beyond surface similarity of the
token. Dense embeddings place rare proper nouns near other rare proper nouns with
similar shape. Full-text has no such failure mode — a lexeme either matches or it
does not.

### 1b. Descriptive, no proper noun — `"wetland birds and flamingos"`

| Retriever | Top 3 |
|---|---|
| Full-text | *(nothing)* |
| Semantic | `bundala_national_park`, `kumana_national_park`, `sinharaja_forest_reserve` |

Full-text returns an **empty set**. The words "wetland", "birds" and "flamingos"
appear nowhere in any name, location or district — the only fields in the
`tsvector`. Semantic search returns exactly the right answer: Bundala is the
country's Ramsar-listed wetland and its main flamingo site.

### 1c. Paraphrase — `"Gathering of elephants at a reservoir"`

| Retriever | Top 3 |
|---|---|
| Full-text | *(nothing)* |
| Semantic | `minneriya_national_park`, `udawalawe_national_park`, `kaudulla_national_park` |

Minneriya ranks first, correctly — "the Gathering" is the specific name for the
seasonal elephant congregation there. The description mentions it, so the meaning
is captured even though no query term matches a name field.

**Conclusion.** 1a is a case where lexical search is strictly better; 1b and 1c
are cases where it returns nothing at all. Neither retriever dominates, which is
what justifies running both and fusing.

---

## 2. A SQL filter is a set, not a ranking

The most instructive bug found during development. The hybrid endpoint originally
treated structured SQL as a fourth ranked list and fed it straight into RRF. On
this query:

> `"where can I see leopards on a safari?"`

it returned **Kumana, Kaudulla, Bundala** — while plain semantic search on the
same query correctly returned **Yala** first. The hybrid path was performing
*worse* than one of the retrievers it was built from.

The cause: `structured_search` returns rows `ORDER BY name`. The router had
correctly inferred `category=national_park`, so SQL returned all ten parks in
alphabetical order, and RRF cannot tell an alphabetical ordering from a relevance
ordering. Bundala sorts first, so it collected the largest possible
reciprocal-rank contribution — `1/(60+1)` — purely for beginning with a B.

The fix is conceptual rather than a tuning change. A SQL filter has no intrinsic
relevance order; it defines *which* rows are eligible, not *how good* they are.
So structured retrieval is now applied as a set intersection over the other
retrievers' ranked lists, after all of them have run:

```python
allowed_ids = {row["id"] for row in structured_rows}
filtered = {name: [i for i in ids if i in allowed_ids]
            for name, ids in ranked_lists.items()}
```

If the intersection is empty the constraint is dropped, so a router that
misreads a district cannot empty the result set.

### Before and after

| Query | Before | After |
|---|---|---|
| leopards on a safari | Kumana, Kaudulla, Bundala | **Yala**, Kumana, Kaudulla |
| beaches in Galle | Unawatuna, Hikkaduwa, Bentota, *Arugam Bay* | Unawatuna, Hikkaduwa, Bentota |
| UNESCO sites in Matale | Sigiriya, Dambulla, Nalanda, Ritigala, *Hikkaduwa Beach* | Sigiriya, Dambulla |

The stray entries in the "before" column are the same defect in a second form:
the image retriever's results were not being constrained by the filter at all, so
a beach could appear under a `historical_site` query on visual similarity alone.

**Takeaway for the report:** RRF fuses *rankings*. Any retriever that does not
produce a genuine relevance ordering should constrain the candidate set instead
of contributing to the fusion.

---

## 3. Worked RRF example

Query: `"UNESCO ancient sites in Matale worth a day trip"` via `/query/hybrid`.

Router output:

```
query_type: hybrid   category: historical_site   district: Matale   unesco_only: true
source:     gemini
reasoning:  "Combines specific administrative district (Matale) and UNESCO tag
             with descriptive criteria (worth a day trip)."
```

Retrievers run: semantic, full-text, image, plus the structured filter.

| Rank | Attraction | RRF score | Found by |
|---|---|---|---|
| 1 | Sigiriya | 0.032787 | semantic, fulltext |
| 2 | Dambulla Cave Temple | 0.032258 | semantic, fulltext |

Both are Matale UNESCO sites, which is exactly the answer set. The structured
filter reduced the candidate pool to the four Matale historical sites, and within
that pool the two retrievers that produce a real ranking agreed on the order.

The score arithmetic is worth spelling out, since it is the mechanism the report
should explain:

```
Sigiriya:  rank 1 semantic  →  1/(60+1) = 0.016393
           rank 1 fulltext  →  1/(60+1) = 0.016393
                                        = 0.032787

Dambulla:  rank 2 semantic  →  1/(60+2) = 0.016129
           rank 2 fulltext  →  1/(60+2) = 0.016129
                                        = 0.032258
```

Agreement across retrievers is what separates the top two from everything else. A
single retriever's confident but wrong answer cannot reach the top of a fused list
unless another retriever agrees with it.

---

## 4. Router accuracy

Eight queries, two per intended class, compared against the keyword heuristic that
serves as the fallback.

| Query | Expected | Gemini | Heuristic |
|---|---|---|---|
| beaches in Galle district | structured | structured ✓ | hybrid ✗ |
| free historical sites | structured | structured ✓ | hybrid ✗ |
| somewhere peaceful to watch birds | semantic | semantic ✓ | semantic ✓ |
| a place with dramatic cliffs and mist | semantic | semantic ✓ | semantic ✓ |
| what does Sigiriya look like? | image | image ✓ | image ✓ |
| show me somewhere that looks like a tropical beach | image | image ✓ | image ✓ |
| which UNESCO sites in Matale are worth a day trip? | hybrid | hybrid ✓ | hybrid ✓ |
| easy hikes in the hill country with good views | hybrid | hybrid ✓ | hybrid ✓ |
| | | **8/8** | **6/8** |

Both agree on the semantic and image classes — those have strong surface cues
("looks like", descriptive phrasing with no proper noun) that a keyword rule
catches as reliably as a model does.

The two failures are both the same mistake: the heuristic classifies *pure filter*
queries as hybrid. Its rule is "names a filter **and** a category → hybrid", and
"beaches in Galle district" satisfies both, so it cannot tell that query apart
from one that also carries a descriptive element. Distinguishing them needs an
understanding that "beaches in Galle" is fully answerable by a WHERE clause while
"beaches in Galle worth a day trip" is not — which is exactly what the model
provides and a keyword rule structurally cannot.

The practical cost of the error is small: a hybrid classification runs extra
retrievers and returns a superset. It is slower and slightly noisier, not wrong.
That is the intended failure mode for a fallback.

Gemini also extracts filters the heuristic misses entirely, such as
`unesco_only: true` from the word "UNESCO" in a sentence where it is not adjacent
to any category term.

---

## 5. Sensitivity to phrasing

Semantic retrieval is not uniformly robust. Two queries with near-identical intent:

| Query | Top result | Bundala's rank |
|---|---|---|
| `"wetland birds and flamingos"` | Bundala ✓ | 1 |
| `"a quiet place to watch migrating birds in wetlands"` | Mirissa Beach ✗ | 4 |

The second phrasing puts **Mirissa Beach** first at similarity 0.3437, ahead of
Kumana (0.3408) and Bundala (0.2826).

The likely cause is the words "quiet" and "place to watch" — Mirissa's description
is dense with watching language (whale watching, sunset viewpoint) and the
structured prefix folded into every document contributes a constant component that
compresses the score range. All four top similarities sit between 0.28 and 0.35,
a narrow band in which ranking is fragile.

This is a real limitation, not a tuning artefact, and it is the clearest argument
for the hybrid path being the default in the UI: adding a second retriever's
opinion is what stabilises a ranking this closely spaced.

**Possible improvements**, none implemented:
- Embed the prose without the structured prefix, and filter structurally instead
- A cross-encoder re-rank over the top 10, which would cost ~100 ms
- More descriptive text per attraction, so vectors separate further

---

## 6. Score ranges observed

| Retriever | Metric | Typical range |
|---|---|---|
| Semantic (MiniLM) | cosine similarity | 0.28 – 0.65 |
| Image (CLIP text→image) | cosine similarity | 0.15 – 0.30 |
| Full-text | `ts_rank` | 0.06 – 0.99 |

These bands are the concrete reason RRF fuses on rank rather than score. A CLIP
similarity of 0.26 is a strong visual match; a MiniLM similarity of 0.26 is close
to noise. Any score-based merge would need per-retriever calibration and would
drift as data was added.

---

## 7. Structured retrieval

Behaves exactly as expected, since it is deterministic SQL.

| Query | Result |
|---|---|
| `category=beach, district=Galle` | Bentota, Hikkaduwa, Unawatuna — all three correct |
| `category=historical_site, unesco_only=true` | The five UNESCO-listed sites only |

The one design decision worth noting is that `district` matches with `ILIKE '%..%'`
rather than equality, because some attractions span two districts
(`Southern/Uva`, `Ratnapura/Monaragala`). Exact matching would silently drop them
from any district filter.

---

## 8. Known limitations

- **Corpus size.** 40 attractions is too small for retrieval metrics like
  precision@k to be meaningful; with 10 items per category, most filtered queries
  can return nearly the whole category.
- **Image coverage is partial: 23 of 40.** Wikimedia rate-limits bulk downloads
  hard, so the set was left incomplete rather than spending hours on backoff.
  Coverage is 8 beaches, 6 mountains, 6 national parks and 3 historical sites, so
  visual search draws on an uneven subset and under-represents historical sites in
  particular. This bounds the image tab only — the other three query types cover
  all 40 attractions, since they retrieve on text.
- **No ground-truth relevance judgements.** Assessment above is qualitative —
  reading results and judging them. A proper evaluation would need a labelled
  query set, which is out of scope at this corpus size.
- **Single-language.** Both the `tsvector` configuration and the embedding models
  are English-only. Sinhala or Tamil queries are unsupported.
- **Router test set is small.** 8 queries, hand-written by the same people who
  wrote the classifier prompt, is enough to show the two paths differ but not
  enough to state an accuracy figure with confidence.
- **Free-tier quota shapes the demo.** The flagship flash model allows roughly 20
  requests per day on the free tier. Routing therefore runs on a lite model with
  a larger allowance, and answer generation falls back to the lite model once the
  flagship budget is spent. Answers get plainer rather than disappearing, but a
  long demo session will cross that line.
