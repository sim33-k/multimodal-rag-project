# API reference

Base URL: `http://localhost:8000`
Interactive docs: `/docs` (Swagger) · `/redoc`

All four query endpoints return the same response shape, so the frontend renders
them with one code path.

---

## Common response

```jsonc
{
  "query": "UNESCO ancient sites in Matale",
  "query_type": "hybrid",
  "route": {                        // only on /query/hybrid
    "query_type": "hybrid",
    "category": "historical_site",
    "district": "Matale",
    "accessibility": null,
    "keywords": "UNESCO ancient sites Matale",
    "free_entry": false,
    "unesco_only": true,
    "reasoning": "Query names a filter and a topic, so retrievers are combined.",
    "source": "gemini"              // or "heuristic" when the API is unavailable
  },
  "results": [ /* Attraction objects */ ],
  "answer": "Sigiriya and the Dambulla Cave Temple...",
  "answer_source": "gemini",        // or "fallback"
  "retrievers_used": ["semantic", "fulltext", "structured"],
  "context": "[1] Sigiriya (historical site)\n    District: Matale\n    ...",
  "result_count": 5
}
```

`context` is the exact text passed to the language model. It is returned so the
retrieval pipeline can be shown to be doing real work, rather than the answer
being taken on trust.

### Attraction object

Core fields are always present. Category-specific fields appear only on rows of
that category — a beach result carries no `height_m` key at all.

```jsonc
{
  "id": "sigiriya",
  "name": "Sigiriya",
  "category": "historical_site",
  "location": "Sigiriya",
  "district": "Matale",
  "latitude": 7.957,
  "longitude": 80.7603,
  "entrance_fee": "USD 30",
  "accessibility": "moderate",
  "best_season": "year-round",

  "historical_period": "5th century AD (Kashyapa era)",
  "architectural_style": "ancient rock fortress",
  "unesco_status": "UNESCO World Heritage Site",

  "images": [{ "file_path": "data/images/historical_sites/sigiriya.jpg",
               "caption": null }],

  "similarity": 0.6421,             // vector retrievers only
  "fusion_score": 0.048916,         // hybrid only
  "retrievers": ["semantic", "fulltext", "structured"]   // hybrid only
}
```

---

## `POST /query/structured`

SQL filters over `attractions_full`. When `query` is non-empty, full-text results
are appended to top up the filtered set.

```jsonc
{
  "query": "",                  // optional keyword, triggers full-text
  "category": "beach",          // beach | mountain | national_park | historical_site
  "district": "Galle",          // partial match, case-insensitive
  "accessibility": "easy",      // easy | moderate | difficult
  "free_entry": false,
  "unesco_only": false,
  "limit": 10,                  // 1-50
  "generate": true              // false skips the LLM call
}
```

```bash
curl -X POST localhost:8000/query/structured \
  -H "Content-Type: application/json" \
  -d '{"category":"beach","district":"Galle","limit":5}'
```

---

## `POST /query/semantic`

Dense retrieval against the MiniLM description embeddings. `category` and
`district` are pushed down into ChromaDB's metadata filter rather than applied
afterwards, so a filtered search still returns a full `limit` of results.

```jsonc
{
  "query": "somewhere quiet to watch birds near a lagoon",
  "category": null,
  "district": null,
  "limit": 10,
  "generate": true
}
```

---

## `POST /query/image`

Text-to-image search through CLIP. Matches the phrase against the **photographs**,
not the descriptions.

```jsonc
{
  "query": "golden sand with palm trees",
  "category": null,
  "limit": 10,
  "generate": true
}
```

## `POST /query/image/upload`

Image-to-image search. `multipart/form-data`, since it carries a file.

| Field | Type | Notes |
|---|---|---|
| `file` | file | jpg, jpeg, png or webp; max 10 MB |
| `limit` | int | default 10 |
| `category` | string | optional, empty string for none |
| `generate` | bool | default true |

```bash
curl -X POST localhost:8000/query/image/upload \
  -F "file=@my_photo.jpg" -F "limit=5"
```

Errors: `400` empty or unreadable file · `413` over 10 MB.

---

## `POST /query/hybrid`

The full pipeline: route, retrieve, fuse, generate. This is the only endpoint that
returns a populated `route` object.

```jsonc
{
  "query": "which UNESCO sites in Matale are worth a day trip?",
  "category": null,          // overrides the router if set
  "district": null,
  "accessibility": null,
  "limit": 10,
  "generate": true
}
```

Filters passed explicitly take precedence over anything the router infers, on the
basis that a deliberate sidebar selection is a stronger signal than the model's
reading of the sentence.

---

## `GET /health`

```json
{
  "status": "ok",
  "database": true,
  "text_collection": 40,
  "image_collection": 40,
  "gemini_configured": true
}
```

`status` is `degraded` when the database is unreachable. Zero collection counts
mean the corresponding embedding script has not been run.

## `GET /filters`

Sidebar dropdown values, read from the loaded data rather than hardcoded, so they
cannot drift out of sync with what is actually in the database.

```json
{
  "categories": ["beach", "mountain", "national_park", "historical_site"],
  "districts": ["Ampara", "Anuradhapura", "Badulla", "..."],
  "accessibility": ["easy", "moderate", "difficult"]
}
```

## `GET /images/{category}/{filename}`

Serves attraction images from `data/images/`. The frontend uses this rather than
reading files off disk, which keeps it free of any filesystem dependency.

```
GET /images/historical_sites/sigiriya.jpg
```

---

## Notes

- CORS is fully permissive. Both services only ever run locally here; this would
  need tightening before any real deployment.
- `generate: false` on any query endpoint skips the LLM call entirely, which is
  the fastest way to time or inspect retrieval on its own.
- There is no authentication. The API is not intended to be exposed beyond
  localhost.
