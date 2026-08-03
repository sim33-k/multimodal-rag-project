# SL Tourism Multimodal RAG

A retrieval augmented search system over Sri Lankan tourist attractions (beaches,
mountains, national parks, historical sites). It combines structured SQL and
full text search in PostgreSQL with text and image embeddings in ChromaDB, merges
the results with Reciprocal Rank Fusion, and generates an answer grounded in what
was actually retrieved.

SCS 4203 Assignment 2, Murshid Bawa (22000224) & Simaak (22001913).

## What it does

There are four query modes:

- Structured: SQL filters over `attractions_full`, plus Postgres `tsvector` full text search. Example: beaches in Galle district with free entry.
- Semantic: MiniLM sentence embeddings in ChromaDB. Example: somewhere quiet to watch birds near a lagoon.
- Image: CLIP embeddings, either upload a photo or describe a scene in words.
- Hybrid: Gemini routes the query, several retrievers run, and the results get merged with RRF. Example: UNESCO sites in Matale worth a day trip.

## Architecture

The browser talks to FastAPI, which never lets the frontend touch Postgres or
ChromaDB directly. A query first goes through the router (Gemini structured
output), which decides which retrievers to call: SQL filters and full text search
against Postgres, or MiniLM/CLIP embedding search against ChromaDB. Whatever comes
back gets merged with Reciprocal Rank Fusion (k=60), turned into context, and
handed to Gemini to write the final answer.

Because everything goes through the API, the whole pipeline can also be tested
directly through the Swagger docs at `/docs` without touching the frontend.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose), so you don't have to install Postgres by hand.
- Python 3.10+ (developed against 3.13).
- Git.
- A free Gemini API key from https://aistudio.google.com/apikey. Optional, see step 3 below.
- No GPU needed. The embedding models run on CPU. First run downloads all-MiniLM-L6-v2 (~90MB) and CLIP ViT-B/32 (~600MB), so make sure you have internet the first time you run the embedding scripts.

## Installation

### 0. Clone the repo

```bash
git clone <this-repo-url>
cd multimodal-rag-project
```

### 1. PostgreSQL via Docker

Both team members run the same container so the environment matches.

```bash
docker compose up -d
```

This starts PostgreSQL 16 on port 5432, database `sltourism`, user
`sltourism_user`, password `devpassword`.

If you don't want to use Docker, install PostgreSQL 16 yourself and create a
matching database and user:

```sql
CREATE DATABASE sltourism;
CREATE USER sltourism_user WITH PASSWORD 'devpassword';
GRANT ALL PRIVILEGES ON DATABASE sltourism TO sltourism_user;
```

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

Then edit `.env` and add a Gemini API key (free, from
https://aistudio.google.com/apikey):

```
GEMINI_API_KEY=your_key_here
DATABASE_URL=postgresql://sltourism_user:devpassword@localhost:5432/sltourism
API_BASE_URL=http://localhost:8000
```

`.env` is gitignored, don't commit it.

Note: the system still runs without a key. Query routing falls back to a keyword
heuristic and answers get composed directly from the retrieved rows instead of
Gemini. Retrieval itself still works fine.

A note on model names and quotas: free tier quotas are per model, and a few
models report zero quota or are closed to new keys, which looks like a bad key
but isn't. The defaults use the `*-latest` aliases since those keep working.
Routing uses a lite model because it runs on every query, while answers use the
flagship flash model, which only gets about 20 free requests a day. You can
override any of these in `.env` with `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL` and
`GEMINI_ROUTER_MODEL`.

### 4. Build the data

```bash
python db/init_db.py               # creates the schema, loads CSVs, registers images
python embeddings/text_embed.py    # MiniLM description embeddings
python embeddings/image_embed.py   # CLIP image embeddings
```

Images are already committed to the repo, so a fresh clone doesn't need to
download anything. Attribution for each image is in
`data/images/IMAGE_SOURCES.md`.

`init_db.py` resets the schema every time it runs, so it's safe to run again
after editing a CSV.

### 5. Run

One command runs everything, the frontend is served by the API itself:

```bash
uvicorn api.main:app --reload --port 8000
```

Then open:

- Web UI: http://localhost:8000/ui
- API docs (Swagger): http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Project layout

```
data/
  raw/                 flat CSVs, one per category
  descriptions/        prose descriptions used for text embeddings
  images/              attraction images + per file source attribution
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
  router.py            Gemini structured output intent classifier
llm/
  context_builder.py   assembles retrieved rows into prompt context
  generate.py          Gemini answer generation
api/
  main.py              app instance, CORS, static images, health
  schemas.py           Pydantic request/response models
  routes/               one module per query type
web/
  index.html           frontend, served by the API at /ui
  style.css            no framework, no external assets
  app.js               no libraries, calls the API over HTTP
```

## Data sources

Attraction data is compiled from public sources including Wikipedia and the Sri
Lanka Tourism Development Authority. Images come from Wikimedia Commons,
per file attribution is written to `data/images/IMAGE_SOURCES.md` by the fetch
script.

Models and libraries used are credited in the technical report.
