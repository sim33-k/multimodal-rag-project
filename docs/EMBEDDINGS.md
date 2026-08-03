# Embedding generation

Two independent vector spaces, both stored in ChromaDB with local persistence
under `embeddings/chroma_store/`.

| Collection | Model | Dimensions | Content |
|---|---|---|---|
| `text_descriptions` | `all-MiniLM-L6-v2` | 384 | One document per attraction |
| `image_embeddings` | `openai/clip-vit-base-patch32` | 512 | One vector per image file |

The two spaces are never compared against each other. A MiniLM vector and a CLIP
vector both describe the same attraction but live in unrelated coordinate systems;
mixing them would produce meaningless distances. They are combined only at the
**rank** level, through Reciprocal Rank Fusion.

## Text embeddings

### Model choice

`all-MiniLM-L6-v2` is a 6-layer distilled sentence transformer, ~90 MB, producing
384-dimensional vectors. It runs comfortably on CPU — encoding all 40 descriptions
takes under two seconds — which matters because neither team machine has a GPU and
the model is re-loaded on every API process start.

Larger models (`all-mpnet-base-v2`, 768-dim) score better on retrieval benchmarks,
but at 40 documents the corpus is far too small for that difference to be
observable, and the latency cost would be paid on every query.

### What gets embedded

Not the raw description. Each document is the description **joined with its
structured fields**:

```
Mirissa Beach. Category: beach. Located in Mirissa, Matara District, Sri Lanka.
Best season: Nov-Apr. Accessibility: easy. A crescent of golden sand on the
south coast fringed by coconut palms...
```

This is a deliberate choice. The descriptions are written as prose and mostly do
not name their own district, so a query like "beaches in the Matara area" would
miss entirely if only the prose were embedded. Folding the structured fields into
the document text makes them semantically searchable without a separate filter.

The cost is a slight dilution — the boilerplate prefix is identical in shape
across all 40 documents, so it contributes a small constant component to every
vector. At this corpus size that is an acceptable trade for the recall gained.

### Normalisation

Vectors are L2-normalised at encode time (`normalize_embeddings=True`) and the
collection is created with `hnsw:space: cosine`. Chroma's default is squared L2,
which would rank by magnitude as well as direction — meaningless for sentence
embeddings, where only direction carries information.

## Image embeddings

### Model choice

CLIP ViT-B/32 maps images **and** text into one shared 512-dimensional space.
That single property is what makes both halves of the image tab work:

- **Image → image.** Encode an uploaded photo, find the nearest stored photos.
- **Text → image.** Encode a phrase, find images that *look* like it.

The second is genuinely distinct from semantic search. Semantic search matches a
query against written descriptions; CLIP text-to-image matches against the pixels.
A query like "golden sand and palm trees" can retrieve a beach whose description
never uses those words, because the model has learned the visual concept.

### Pipeline

```
data/images/<category>/<id>.jpg
        │
        ├─ registered in the `images` table by db/init_db.py
        │
        ▼
  CLIP image encoder ──▶ 512-d vector ──▶ chroma `image_embeddings`
                                            id:       img_<image_id>
                                            metadata: attraction_id, name,
                                                      category, district, path
```

The Chroma id is the **image** id, not the attraction id, because one attraction
can have several images. The attraction is carried in metadata so results can be
collapsed back per attraction at query time — `retrieval/image_search.py` keeps
each attraction's best-matching image and discards the rest, so a place with two
photos cannot occupy two of the top slots.

Images are batched 16 at a time so memory stays flat as the set grows, and
downscaled to 1024 px on the long edge at download time. CLIP resizes to 224×224
internally, so storing full resolution would buy nothing.

### Version handling

`transformers` 4.x returns a bare tensor from `get_image_features`; 5.x returns a
`BaseModelOutputWithPooling` whose `pooler_output` holds the projected embedding.
`embeddings/image_embed.py:_as_tensor()` handles both, so the pipeline works
regardless of which version is installed.

## Rebuilding

Both scripts drop and recreate their collection on every run, so a re-ingest never
leaves stale vectors from deleted or renamed attractions.

```bash
python -m embeddings.text_embed     # after editing descriptions or CSVs
python -m embeddings.image_embed    # after adding or replacing images
```

`image_embed` reads the `images` table, so new image files must be registered by
`db.init_db` first.

## Query-time encoding

Both modules expose the encoder used at ingest, so query vectors are produced by
exactly the same model and normalisation as the stored ones:

- `embeddings.text_embed.embed_query(text)` → 384-d
- `embeddings.image_embed.embed_image(pil_image)` → 512-d
- `embeddings.image_embed.embed_text(text)` → 512-d

Models are loaded lazily and cached per process. The first query after a server
start pays the model load; subsequent ones do not.

## Credits

| Component | Source |
|---|---|
| `all-MiniLM-L6-v2` | sentence-transformers, Reimers & Gurevych |
| `openai/clip-vit-base-patch32` | OpenAI, via Hugging Face `transformers` |
| ChromaDB | Chroma |
| Reciprocal Rank Fusion | Cormack, Clarke & Büttcher (2009) |
