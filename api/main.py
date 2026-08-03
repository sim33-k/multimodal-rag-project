"""FastAPI application: mounts the four query routers and serves attraction images.

The Streamlit frontend talks only to this API and never opens a database or
ChromaDB connection of its own. That boundary is what lets the retrieval pipeline
be demonstrated on its own through the generated docs at /docs.

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

# Streamlit runs on a different port, so it is a cross-origin caller. The origin
# list is permissive because both services only ever run locally here.
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

    Used by the Streamlit sidebar to tell the user what is missing when results
    come back empty, rather than silently returning nothing.
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
        "endpoints": [
            "POST /query/structured",
            "POST /query/semantic",
            "POST /query/image",
            "POST /query/image/upload",
            "POST /query/hybrid",
        ],
    }
