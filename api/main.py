from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import hybrid, image, semantic, structured
from api.schemas import FilterOptions, HealthResponse
from db.connection import PROJECT_ROOT, ping
from embeddings import IMAGE_COLLECTION, TEXT_COLLECTION, get_collection
from llm.generate import is_configured
from retrieval.sql_query import filter_options

app = FastAPI(title="SL Tourism Multimodal RAG API", description="Retrieval augmented search over Sri Lankan tourist attractions combining PostgreSQL structured and full text search with ChromaDB text and image embeddings.", version="0.1.0")


# wide open but this only ever runs on localhost so the frontend still works opening index.html straight off disk
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

# frontend asks the API for images instead of reading the folder itself
IMAGES_DIR = PROJECT_ROOT / "data" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(IMAGES_DIR)), name="images")

# serving the page from here too means its same origin and no second server to start
WEB_DIR = PROJECT_ROOT / "web"
if WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")

app.include_router(structured.router, prefix="/query", tags=["query"])
app.include_router(semantic.router, prefix="/query", tags=["query"])
app.include_router(image.router, prefix="/query", tags=["query"])
app.include_router(hybrid.router, prefix="/query", tags=["query"])


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    # so an unconfigured system doesnt just look like an empty database
    database_ok = ping()

    try:
        text_count = get_collection(TEXT_COLLECTION).count()
    except Exception:
        text_count = 0

    try:
        image_count = get_collection(IMAGE_COLLECTION).count()
    except Exception:
        image_count = 0

    return HealthResponse(status="ok" if database_ok else "degraded", database=database_ok, text_collection=text_count, image_collection=image_count, gemini_configured=is_configured())


@app.get("/filters", response_model=FilterOptions, tags=["system"])
def filters() -> FilterOptions:
    return FilterOptions(**filter_options())


@app.get("/", tags=["system"])
def root() -> dict:
    endpoints = ["POST /query/structured", "POST /query/semantic", "POST /query/image", "POST /query/image/upload", "POST /query/hybrid"]
    return {"name": "SL Tourism Multimodal RAG API", "docs": "/docs", "ui": "/ui", "endpoints": endpoints}
