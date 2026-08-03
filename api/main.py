# FastAPI app. Mounts the four query routes, serves the images and the frontend.
#
# Run:  uvicorn api.main:app --reload --port 8000

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

# wide open, but everything here only ever runs on localhost. it's here so the
# frontend still works if you open index.html straight off disk
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# the frontend asks the API for images rather than reading the folder itself
IMAGES_DIR = PROJECT_ROOT / "data" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

# serving the page from here too means it's same origin and there's no second
# server to start
WEB_DIR = PROJECT_ROOT / "web"
if WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

app.include_router(structured.router, prefix="/query", tags=["query"])
app.include_router(semantic.router, prefix="/query", tags=["query"])
app.include_router(image.router, prefix="/query", tags=["query"])
app.include_router(hybrid.router, prefix="/query", tags=["query"])


def collection_count(name):
    try:
        return get_collection(name).count()
    except Exception:
        return 0


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    # so an unconfigured system doesn't just look like an empty database
    database_ok = ping()
    return HealthResponse(
        status="ok" if database_ok else "degraded",
        database=database_ok,
        text_collection=collection_count(TEXT_COLLECTION),
        image_collection=collection_count(IMAGE_COLLECTION),
        gemini_configured=is_configured(),
    )


@app.get("/filters", response_model=FilterOptions, tags=["system"])
def filters() -> FilterOptions:
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
