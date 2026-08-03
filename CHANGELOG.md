# Changelog

All notable changes to this project are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Entries describe behaviour, not files touched — git already records the files.
Update this in the same commit as the change rather than batching entries at the end.

## [Unreleased]

### Added
- Plain HTML/CSS/JS frontend under `web/`, served by the API at `/ui`. No
  framework, no libraries, no external assets — one `uvicorn` command runs the
  whole system. Covers the same features as the Streamlit client: sidebar
  filters, four query tabs, result cards, photo gallery, map and the retrieved
  context panel
- Map drawn as inline SVG with a hand-projected coastline, so the page has no CDN
  dependency and works with no internet connection

### Removed
- The Streamlit frontend and everything only it used: `app/`, `.streamlit/`, and
  the `streamlit`, `pydeck`, `pandas` and `httpx` dependencies. The plain HTML
  client covers the same features and is served by the API, so the system now
  runs from one command instead of two processes

### To do
- Complete the image set for all 40 attractions and rebuild image embeddings
- Verify CSV facts (coordinates, fees, seasons) against a second source
- Record the demonstration video covering all four query types
- Write the technical report from the `docs/` write-ups

## [0.1.0] - 2026-08-02

First working end-to-end pipeline: all four query types return results through
the API, and the Streamlit frontend renders them.

### Added

**Database**
- PostgreSQL 16 via Docker Compose, with a healthcheck so dependent steps can wait
- Normalised schema using the supertype/subtype pattern: a core `attractions`
  table plus one detail table per category, joined 1:1
- `attractions_full` view flattening the joins, so application code never writes them
- Generated `tsvector` column over name, location and district, with a GIN index
- `db/init_db.py` splits flat CSV rows into core and detail tables on import, and
  registers image files by matching filenames to attraction ids

**Data**
- 40 attractions, 10 per category, as flat editable CSVs
- Hand-written descriptions per attraction, used as the text-embedding documents
- `data/fetch_images.py` downloads images from Wikimedia Commons, batching title
  lookups 50 at a time and recording per-file attribution for the report

**Embeddings**
- Text: `all-MiniLM-L6-v2` over descriptions joined with name, category and district,
  so structured fields are searchable semantically
- Image: CLIP `openai/clip-vit-base-patch32`, supporting both image-to-image and
  text-to-image search in a shared vector space
- Both collections use cosine distance and are rebuilt from scratch per ingest

**Retrieval**
- Structured SQL filters over `attractions_full`, all values bound as parameters
- Postgres full-text search with an OR-term fallback when the strict
  `websearch_to_tsquery` match returns nothing
- Semantic search with metadata filters pushed down into ChromaDB
- Image search collapsing multiple images per attraction to the best match
- Reciprocal Rank Fusion (k=60) merging ranked lists by position, not by score
- Structured SQL applied as a set intersection over the fused candidates rather
  than as a ranked list, since a SQL result has no intrinsic relevance order
- Gemini structured-output router classifying intent and extracting filters, with
  a keyword heuristic behind it

**API**
- FastAPI backend: `/query/structured`, `/query/semantic`, `/query/image`,
  `/query/image/upload`, `/query/hybrid`
- `/health` reporting database, collection counts and Gemini configuration
- `/filters` serving sidebar values derived from the data
- Attraction images served from `/images`, so the frontend needs no disk access
- Every response carries the retrieved context and which retrievers ran

**Frontend**
- Streamlit UI communicating only over HTTP, never touching the database
- Custom ocean-teal and terracotta theme via injected CSS
- Result cards, pydeck map coloured by category, and a collapsible panel showing
  the exact context passed to the language model
- Photo gallery on the image tab, since for a visual query the images are the
  result rather than an illustration of it

**Documentation**
- README with installation and run instructions
- `docs/` covering architecture, database design, embeddings, API and evaluation

### Fixed
- Gemini calls always fell back despite a valid API key. The configured model,
  `gemini-2.0-flash`, reports a zero free-tier quota, and `gemini-2.5-flash` is
  closed to new keys — both fail in ways that look like an authentication problem
  but are not. Switched to the `*-latest` aliases, which keep working
- Routing and answer generation now use different models. Free-tier quotas are
  per-model and the flagship flash model allows only ~20 requests/day; routing
  runs on every query, so it uses a lite model with a larger allowance and leaves
  the flagship budget for answers. Generation falls back to the lite model before
  dropping to the non-LLM path, so answers get plainer rather than disappearing
- Hybrid results were ranked by an alphabetical artefact. Structured SQL was
  being fused as a ranked list, so `"where can I see leopards on a safari?"`
  returned Kumana ahead of Yala — worse than semantic search alone. Structured
  retrieval now filters rather than ranks. Details in `docs/EVALUATION.md`
- Image search results were not constrained by the active filters, so a beach
  could appear in a historical-site query on visual similarity alone
- CLIP feature extraction under `transformers` 5.x, which returns a model output
  object where 4.x returned a bare tensor

### Notes
- The system degrades rather than fails without a Gemini key: routing falls back
  to keyword heuristics and answers are composed from the retrieved rows
- `google-generativeai` is deprecated upstream but is what the project spec
  locks; migrating to `google-genai` is a post-submission change
