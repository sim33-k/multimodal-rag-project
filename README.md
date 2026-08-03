# SL Tourism Multimodal RAG

A retrieval-augmented search system over Sri Lankan tourist attractions across four
categories — beaches, mountains, national parks and historical sites. It combines
structured SQL and full-text search in PostgreSQL with text and image embeddings in
ChromaDB, merges the ranked results with Reciprocal Rank Fusion, and generates a
grounded natural-language answer.

**SCS 4203 Assignment 2** · Murshid & Simaak

---

## What it does

Four query modes, each backed by its own retrieval strategy:

| Mode | Retriever | Example query |
|---|---|---|
| **Structured** | SQL filters over `attractions_full`, plus Postgres `tsvector` full-text | beaches in Galle district with free entry |
| **Semantic** | MiniLM sentence embeddings in ChromaDB | somewhere quiet to watch birds near a lagoon |
| **Image** | CLIP embeddings — upload a photo, or describe a scene | *(upload a beach photo)* |
| **Hybrid** | Gemini routes the query, multiple retrievers run, RRF merges them | UNESCO sites in Matale worth a day trip |

---

## Architecture

```
Browser UI  ──HTTP──▶  FastAPI  ──▶  router (Gemini structured output)
                                          │
                            ┌─────────────┼─────────────┬──────────────┐
                            ▼             ▼             ▼              ▼
                       SQL filters   full-text     MiniLM text     CLIP image
                       (Postgres)    (tsvector)    (ChromaDB)      (ChromaDB)
                            └─────────────┴──────┬──────┴──────────────┘
                                                 ▼
                                    Reciprocal Rank Fusion (k=60)
                                                 ▼
                                    context builder ──▶ Gemini ──▶ answer
```

The frontend never touches PostgreSQL or ChromaDB directly. It only calls the API,
which means the whole retrieval pipeline is independently demonstrable through the
auto-generated Swagger docs at `/docs`.

Detailed write-ups live in [docs/](docs/):
[architecture](docs/ARCHITECTURE.md) ·
[database design](docs/DATABASE.md) ·
[embeddings](docs/EMBEDDINGS.md) ·
[API reference](docs/API.md) ·
[evaluation](docs/EVALUATION.md)

---

## Installation

### 1. PostgreSQL via Docker

Both team members run the same container, so the environment is identical.

```bash
docker compose up -d
```

This starts PostgreSQL 16 on port 5432 with database `sltourism`, user
`sltourism_user`, password `devpassword`.

<details>
<summary>No Docker? Native PostgreSQL fallback</summary>

Install PostgreSQL 16 and create a matching database and user:

```sql
CREATE DATABASE sltourism;
CREATE USER sltourism_user WITH PASSWORD 'devpassword';
GRANT ALL PRIVILEGES ON DATABASE sltourism TO sltourism_user;
```
</details>

### 2. Python environment

Requires Python 3.10 or newer.

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configuration

```bash
cp .env.example .env
```

Then edit `.env` and add a Gemini API key — free from
<https://aistudio.google.com/apikey>:

```
GEMINI_API_KEY=your_key_here
DATABASE_URL=postgresql://sltourism_user:devpassword@localhost:5432/sltourism
API_BASE_URL=http://localhost:8000
```

`.env` is gitignored and must never be committed.

> The system runs without a key: query routing falls back to a keyword heuristic
> and answers are composed directly from the retrieved rows. Retrieval itself is
> unaffected. See [graceful degradation](docs/ARCHITECTURE.md#graceful-degradation).

**On model names and quotas.** Free-tier quotas are per-model and several models
report a zero quota or are closed to new API keys — which fails in a way that
looks like a bad key but is not. The defaults use the `*-latest` aliases, which
keep working. Routing uses a lite model because it runs on every query, while
answers use the flagship flash model, whose free-tier allowance is only about 20
requests per day. Override any of them in `.env` via `GEMINI_MODEL`,
`GEMINI_FALLBACK_MODEL` and `GEMINI_ROUTER_MODEL`.

### 4. Build the data

```bash
python db/init_db.py               # creates the schema, loads CSVs, registers images
python embeddings/text_embed.py    # MiniLM description embeddings
python embeddings/image_embed.py   # CLIP image embeddings
```

Images are committed to the repository, so a fresh clone needs no downloads.

`init_db.py` resets the schema on every run, so it is safe to re-run after editing
a CSV.

To add or refresh images:

```bash
python data/fetch_images.py        # skips files it already has
python db/init_db.py               # re-register
python embeddings/image_embed.py   # re-embed
```

> Wikimedia rate-limits bulk downloads aggressively and the script backs off when
> it hits that. A run may fetch only part of the set — re-run it later and it will
> resume where it stopped. Attribution accumulates in
> `data/images/IMAGE_SOURCES.md` across runs.

### 5. Run

One command runs everything — the frontend is served by the API itself:

```bash
uvicorn api.main:app --reload --port 8000
```

| | |
|---|---|
| Web UI | <http://localhost:8000/ui> |
| API docs (Swagger) | <http://localhost:8000/docs> |
| Health check | <http://localhost:8000/health> |

---

## Project layout

```
data/
  raw/                 flat CSVs, one per category
  descriptions/        prose descriptions used for text embeddings
  images/              attraction images + per-file source attribution
  fetch_images.py      rebuilds or tops up the image set from Wikimedia
db/
  schema.sql           normalised schema, attractions_full view, tsvector column
  init_db.py           creates the schema and loads the CSVs
  connection.py        shared SQLAlchemy engine
embeddings/
  text_embed.py        MiniLM description embeddings
  image_embed.py       CLIP image embeddings
  chroma_store/        persisted vectors (gitignored)
retrieval/
  sql_query.py         structured filters over attractions_full
  fulltext_search.py   Postgres tsvector search
  semantic_search.py   ChromaDB text search
  image_search.py      ChromaDB image search
  hybrid_fusion.py     Reciprocal Rank Fusion
  router.py            Gemini structured-output intent classifier
llm/
  context_builder.py   assembles retrieved rows into prompt context
  generate.py          Gemini answer generation
api/
  main.py              app instance, CORS, static images, health
  schemas.py           Pydantic request/response models
  routes/              one module per query type
web/
  index.html           frontend, served by the API at /ui
  style.css            no framework, no external assets
  app.js               no libraries; calls the API over HTTP
docs/                  architecture, database, embeddings, API, evaluation
```

---

## Health check

`GET /health` reports what is configured, which is the fastest way to diagnose
empty results:

```json
{
  "status": "ok",
  "database": true,
  "text_collection": 40,
  "image_collection": 23,
  "gemini_configured": true
}
```

`text_collection: 0` means `embeddings.text_embed` has not been run.
`image_collection: 0` means images have not been fetched or embedded.

All 40 attractions are text-searchable. `image_collection` is lower because
Wikimedia rate-limiting left part of the image set undownloaded — this affects the
image tab only; structured, semantic and hybrid search cover all four categories
regardless. Re-run `python data/fetch_images.py` to top it up.

---

## Data sources

Attraction data is compiled from public sources including Wikipedia and the Sri
Lanka Tourism Development Authority. Images are retrieved from Wikimedia Commons;
per-file attribution is written to `data/images/IMAGE_SOURCES.md` by the fetch
script.

Models and libraries used are credited in [docs/EMBEDDINGS.md](docs/EMBEDDINGS.md)
and in the technical report.
