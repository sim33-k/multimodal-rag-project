"""FastAPI application: mounts the four query routers and serves attraction images.

The frontend talks only to this API and never opens a database or ChromaDB
connection of its own. That boundary is what lets the retrieval pipeline be
demonstrated on its own through the generated docs at /docs.

Run with:  uvicorn api.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import hybrid, image, semantic, structured
from api.schemas import FilterOptions, HealthResponse
from db.connection import PROJECT_ROOT, ping
from embeddings import IMAGE_COLLECTION, TEXT_COLLECTION, get_collection
from llm.generate import is_configured
from retrieval.sql_query import filter_options

app = FastAPI(
    title="SL Tourism Multimodal RAG API",
    description=(
        "Retrieval-augmented search over Sri Lankan tourist attractions, combining "
        "PostgreSQL structured and full-text search with ChromaDB text and image "
        "embeddings."
    ),
    version="0.1.0",
)

# The bundled frontend is same-origin, but CORS stays open so the API can also be
# called from a page opened straight off disk during development. Everything here
# only ever runs locally.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Images are served from the API rather than read off disk by the frontend, so the
# frontend needs no filesystem access and the boundary stays clean.
IMAGES_DIR = PROJECT_ROOT / "data" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

# The frontend, served from the API itself at /ui, so requests are same-origin and
# no second server has to be started. It reaches the data only through the HTTP
# endpoints below - it has no privileged access of any kind.
WEB_DIR = PROJECT_ROOT / "web"
if WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

app.include_router(structured.router, prefix="/query", tags=["query"])
app.include_router(semantic.router, prefix="/query", tags=["query"])
app.include_router(image.router, prefix="/query", tags=["query"])
app.include_router(hybrid.router, prefix="/query", tags=["query"])


def _collection_count(name: str) -> int:
    try:
        return get_collection(name).count()
    except Exception:
        return 0


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Report which backing services are reachable and populated.

    The frontend uses this to say what is missing when results come back empty,
    rather than leaving an unconfigured system looking like an empty database.
    """
    database_ok = ping()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        database=database_ok,
        text_collection=_collection_count(TEXT_COLLECTION),
        image_collection=_collection_count(IMAGE_COLLECTION),
        gemini_configured=is_configured(),
    )


@app.get("/filters", response_model=FilterOptions, tags=["system"])
def filters() -> FilterOptions:
    """Values for the sidebar dropdowns, derived from the data rather than hardcoded."""
    return FilterOptions(**filter_options())


@app.get("/", tags=["system"])
def root() -> dict:
    return {
        "name": "SL Tourism Multimodal RAG API",
        "docs": "/docs",
        "ui": "/ui",
        "endpoints": [
            "POST /query/structured",
            "POST /query/semantic",
            "POST /query/image",
            "POST /query/image/upload",
            "POST /query/hybrid",
        ],
    }
