"""Pydantic request and response models for the API.

Defining these explicitly rather than returning bare dicts is what gives the
FastAPI /docs page its schemas, which makes the API independently demonstrable
without the frontend.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

QueryType = Literal["structured", "semantic", "image", "hybrid"]
Category = Literal["beach", "mountain", "national_park", "historical_site"]
Accessibility = Literal["easy", "moderate", "difficult"]


class Attraction(BaseModel):
    """One retrieved attraction.

    The category-specific columns are optional because a beach row carries none of
    the mountain fields; the retrieval layer strips them before they reach here.
    """

    id: str
    name: str
    category: str
    location: str | None = None
    district: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    entrance_fee: str | None = None
    accessibility: str | None = None
    best_season: str | None = None

    # Beach
    activity_type: str | None = None
    water_quality: str | None = None
    surf_break: bool | None = None
    # Mountain
    height_m: float | None = None
    trekking_difficulty: str | None = None
    duration_hours: float | None = None
    # National park
    conservation_status: str | None = None
    habitat: str | None = None
    area_sq_km: float | None = None
    notable_wildlife: str | None = None
    # Historical site
    historical_period: str | None = None
    architectural_style: str | None = None
    unesco_status: str | None = None

    images: list[dict[str, Any]] = Field(default_factory=list)

    # Present only on results that came through a vector or fusion retriever.
    similarity: float | None = None
    fusion_score: float | None = None
    retrievers: list[str] | None = None


class RouteInfo(BaseModel):
    """How the router classified the query, surfaced so the UI can display it."""

    query_type: QueryType
    category: str | None = None
    district: str | None = None
    accessibility: str | None = None
    keywords: str = ""
    free_entry: bool = False
    unesco_only: bool = False
    reasoning: str = ""
    source: str = "heuristic"


class StructuredQueryRequest(BaseModel):
    query: str = ""
    category: Category | None = None
    district: str | None = None
    accessibility: Accessibility | None = None
    free_entry: bool = False
    unesco_only: bool = False
    limit: int = Field(default=10, ge=1, le=50)
    generate: bool = True


class SemanticQueryRequest(BaseModel):
    query: str
    category: Category | None = None
    district: str | None = None
    limit: int = Field(default=10, ge=1, le=50)
    generate: bool = True


class ImageQueryRequest(BaseModel):
    """Text-driven visual search. Uploading a file uses the multipart endpoint."""

    query: str
    category: Category | None = None
    limit: int = Field(default=10, ge=1, le=50)
    generate: bool = True


class HybridQueryRequest(BaseModel):
    query: str
    category: Category | None = None
    district: str | None = None
    accessibility: Accessibility | None = None
    limit: int = Field(default=10, ge=1, le=50)
    generate: bool = True


class QueryResponse(BaseModel):
    """Uniform response for all four query types.

    `retrievers_used` and `context` are included so the demo can show the
    retrieved evidence, not just the final answer.
    """

    query: str
    query_type: QueryType
    route: RouteInfo | None = None
    results: list[Attraction]
    answer: str | None = None
    answer_source: str | None = None
    retrievers_used: list[str] = Field(default_factory=list)
    context: str | None = None
    result_count: int = 0


class FilterOptions(BaseModel):
    categories: list[str]
    districts: list[str]
    accessibility: list[str]


class HealthResponse(BaseModel):
    status: str
    database: bool
    text_collection: int
    image_collection: int
    gemini_configured: bool
