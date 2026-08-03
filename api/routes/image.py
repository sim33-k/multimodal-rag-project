"""Image queries: visual similarity search over CLIP embeddings.

Two endpoints because the two inputs are shaped differently. An uploaded file has
to arrive as multipart, while a text phrase is ordinary JSON. Both encode into the
same CLIP space and hit the same collection.
"""

import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from api.routes import build_response
from api.schemas import ImageQueryRequest, QueryResponse
from retrieval import image_search

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@router.post("/image", response_model=QueryResponse)
def image_text_query(request: ImageQueryRequest) -> QueryResponse:
    """Find attractions that *look* like a described scene.

    Distinct from /query/semantic: this matches the phrase against the photographs
    themselves, so it can retrieve a place whose written description never uses
    the words in the query.
    """
    rows = image_search.search_by_text(
        query=request.query, limit=request.limit, category=request.category
    )

    return build_response(
        query=request.query,
        query_type="image",
        rows=rows,
        retrievers_used=["image_text"],
        generate=request.generate,
    )


@router.post("/image/upload", response_model=QueryResponse)
async def image_upload_query(
    file: UploadFile = File(...),
    limit: int = Form(10),
    category: str | None = Form(None),
    generate: bool = Form(True),
) -> QueryResponse:
    """Find attractions visually similar to an uploaded photograph."""
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image must be under 10MB.")

    try:
        image = Image.open(io.BytesIO(payload)).convert("RGB")
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=400, detail="That file could not be read as an image."
        )

    rows = image_search.search_by_image(
        image=image, limit=limit, category=category or None
    )

    return build_response(
        query=f"Uploaded image: {file.filename}",
        query_type="image",
        rows=rows,
        retrievers_used=["image_upload"],
        generate=generate,
    )
