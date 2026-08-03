# Structured search - filtered SQL against the attractions_full view.
# Always uses bound parameters, never string formatting, so nothing coming from
# the LLM router can mess with the query.

from db.connection import fetch_all

# The columns that only apply to one category. The view LEFT JOINs everything so
# a beach row comes back with NULL height_m etc, and we strip those out below.
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


def clean_row(row):
    # drop the other categories' columns, then drop anything that's None
    keep = set(CORE_FIELDS)
    keep.update(CATEGORY_DETAIL_COLUMNS.get(row.get("category"), []))

    cleaned = {}
    for key in row:
        if key in keep and row[key] is not None:
            cleaned[key] = row[key]
    return cleaned


def attach_images(rows):
    # one query for all of them instead of one per row
    if not rows:
        return rows

    ids = [row["id"] for row in rows]
    images = fetch_all(
        "SELECT attraction_id, file_path, caption FROM images "
        "WHERE attraction_id = ANY(:ids) ORDER BY image_id",
        {"ids": ids},
    )

    grouped = {}
    for image in images:
        aid = image["attraction_id"]
        if aid not in grouped:
            grouped[aid] = []
        grouped[aid].append({
            "file_path": image["file_path"],
            "caption": image["caption"],
        })

    for row in rows:
        row["images"] = grouped.get(row["id"], [])
    return rows


def structured_search(category=None, district=None, accessibility=None,
                      best_season=None, keyword=None, max_height_m=None,
                      min_height_m=None, unesco_only=False, surf_break=None,
                      free_entry=False, limit=10):
    # only the filters that were actually passed get added to the WHERE, so
    # calling this with nothing gives you a general listing
    clauses = []
    params = {"limit": limit}

    if category:
        clauses.append("category = :category")
        params["category"] = category
    if district:
        # some districts are stored as "Southern/Uva" so match on contains
        clauses.append("district ILIKE :district")
        params["district"] = "%" + district + "%"
    if accessibility:
        clauses.append("accessibility = :accessibility")
        params["accessibility"] = accessibility
    if best_season:
        clauses.append("best_season ILIKE :best_season")
        params["best_season"] = "%" + best_season + "%"
    if keyword:
        clauses.append("(name ILIKE :keyword OR location ILIKE :keyword)")
        params["keyword"] = "%" + keyword + "%"
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

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    rows = fetch_all(
        "SELECT * FROM attractions_full " + where + " ORDER BY name LIMIT :limit",
        params,
    )
    return attach_images([clean_row(r) for r in rows])


def get_by_ids(ids):
    # used to turn the ids from the vector searches back into full rows,
    # keeping the order they came in
    if not ids:
        return []

    rows = fetch_all("SELECT * FROM attractions_full WHERE id = ANY(:ids)",
                     {"ids": ids})

    by_id = {}
    for row in rows:
        by_id[row["id"]] = clean_row(row)

    ordered = []
    for key in ids:
        if key in by_id:
            ordered.append(by_id[key])
    return attach_images(ordered)


def filter_options():
    # for the dropdowns in the UI, read from the data so they can't go stale
    districts = fetch_all(
        "SELECT DISTINCT district FROM attractions "
        "WHERE district IS NOT NULL ORDER BY district"
    )
    return {
        "categories": ["beach", "mountain", "national_park", "historical_site"],
        "districts": [r["district"] for r in districts],
        "accessibility": ["easy", "moderate", "difficult"],
    }
