"""Structured retrieval: filtered SQL against the attractions_full view.

Every query here reads from the view rather than joining the detail tables by
hand, so adding a category means changing schema.sql and nothing in this file.
Filters are always passed as bound parameters, never string-formatted into the
SQL, so a value coming from the LLM router cannot alter the query structure.
"""

from db.connection import fetch_all

# Detail columns that only apply to one category. They come back NULL for every
# other category through the view's LEFT JOINs, and are stripped before the row
# is returned so a beach result is not padded with empty mountain fields.
CATEGORY_DETAIL_COLUMNS = {
    "beach": ["activity_type", "water_quality", "surf_break"],
    "mountain": ["height_m", "trekking_difficulty", "duration_hours"],
    "national_park": [
        "conservation_status",
        "habitat",
        "area_sq_km",
        "notable_wildlife",
    ],
    "historical_site": ["historical_period", "architectural_style", "unesco_status"],
}

ALL_DETAIL_COLUMNS = [
    column for columns in CATEGORY_DETAIL_COLUMNS.values() for column in columns
]

CORE_FIELDS = [
    "id",
    "name",
    "category",
    "location",
    "district",
    "latitude",
    "longitude",
    "entrance_fee",
    "accessibility",
    "best_season",
]


def clean_row(row: dict) -> dict:
    """Drop the detail columns that belong to other categories, plus bookkeeping."""
    keep = set(CORE_FIELDS) | set(CATEGORY_DETAIL_COLUMNS.get(row.get("category"), []))
    cleaned = {key: value for key, value in row.items() if key in keep}
    # Also drop keys that are genuinely empty for this attraction so the LLM
    # context and the UI cards are not cluttered with nulls.
    return {key: value for key, value in cleaned.items() if value is not None}


def attach_images(rows: list[dict]) -> list[dict]:
    """Add each attraction's image paths in one query rather than one query per row."""
    if not rows:
        return rows

    ids = [row["id"] for row in rows]
    images = fetch_all(
        "SELECT attraction_id, file_path, caption FROM images "
        "WHERE attraction_id = ANY(:ids) ORDER BY image_id",
        {"ids": ids},
    )

    grouped: dict[str, list[dict]] = {}
    for image in images:
        grouped.setdefault(image["attraction_id"], []).append(
            {"file_path": image["file_path"], "caption": image["caption"]}
        )

    for row in rows:
        row["images"] = grouped.get(row["id"], [])
    return rows


def structured_search(
    category: str | None = None,
    district: str | None = None,
    accessibility: str | None = None,
    best_season: str | None = None,
    keyword: str | None = None,
    max_height_m: float | None = None,
    min_height_m: float | None = None,
    unesco_only: bool = False,
    surf_break: bool | None = None,
    free_entry: bool = False,
    limit: int = 10,
) -> list[dict]:
    """Filtered lookup over attractions_full.

    Only the filters that were actually supplied contribute a WHERE clause, so an
    empty filter set returns a general listing rather than nothing.
    """
    clauses: list[str] = []
    params: dict = {"limit": limit}

    if category:
        clauses.append("category = :category")
        params["category"] = category
    if district:
        # Districts are stored as free text and some span two ("Southern/Uva"),
        # so this matches on containment rather than equality.
        clauses.append("district ILIKE :district")
        params["district"] = f"%{district}%"
    if accessibility:
        clauses.append("accessibility = :accessibility")
        params["accessibility"] = accessibility
    if best_season:
        clauses.append("best_season ILIKE :best_season")
        params["best_season"] = f"%{best_season}%"
    if keyword:
        clauses.append("(name ILIKE :keyword OR location ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"
    if max_height_m is not None:
        clauses.append("height_m <= :max_height_m")
        params["max_height_m"] = max_height_m
    if min_height_m is not None:
        clauses.append("height_m >= :min_height_m")
        params["min_height_m"] = min_height_m
    if unesco_only:
        clauses.append("unesco_status ILIKE '%UNESCO%'")
    if surf_break is not None:
        clauses.append("surf_break = :surf_break")
        params["surf_break"] = surf_break
    if free_entry:
        clauses.append("entrance_fee ILIKE 'free%'")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = fetch_all(
        f"SELECT * FROM attractions_full {where} ORDER BY name LIMIT :limit", params
    )
    return attach_images([clean_row(row) for row in rows])


def get_by_ids(ids: list[str]) -> list[dict]:
    """Hydrate ids returned by the vector retrievers into full rows, order preserved."""
    if not ids:
        return []

    rows = fetch_all(
        "SELECT * FROM attractions_full WHERE id = ANY(:ids)", {"ids": ids}
    )
    by_id = {row["id"]: clean_row(row) for row in rows}
    ordered = [by_id[key] for key in ids if key in by_id]
    return attach_images(ordered)


def filter_options() -> dict[str, list[str]]:
    """Distinct values for the sidebar dropdowns, read from the data itself."""
    districts = fetch_all(
        "SELECT DISTINCT district FROM attractions "
        "WHERE district IS NOT NULL ORDER BY district"
    )
    return {
        "categories": ["beach", "mountain", "national_park", "historical_site"],
        "districts": [row["district"] for row in districts],
        "accessibility": ["easy", "moderate", "difficult"],
    }
