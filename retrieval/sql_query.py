# structured search just filtered SQL on the attractions_full view
# params always bound we never paste string directly into query

from db.connection import fetch_all

# these columns only belong to one category other ones just come as None
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

CORE_FIELDS = ["id", "name", "category", "location", "district", "latitude", "longitude", "entrance_fee", "accessibility", "best_season"]


def clean_row(row):
    # keep the shared columns and whatever this category needs drop None ones
    category = row.get("category")

    keep = []
    for field in CORE_FIELDS:
        keep.append(field)
    if category in CATEGORY_DETAIL_COLUMNS:
        for field in CATEGORY_DETAIL_COLUMNS[category]:
            keep.append(field)

    cleaned = {}
    for key in row:
        if key in keep and row[key] is not None:
            cleaned[key] = row[key]
    return cleaned


def attach_images(rows):
    # doing one query for all rows so we dont hit db one time per row
    if not rows:
        return rows

    ids = []
    for row in rows:
        ids.append(row["id"])

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
        if row["id"] in grouped:
            row["images"] = grouped[row["id"]]
        else:
            row["images"] = []
    return rows


def structured_search(category=None, district=None, accessibility=None,
                      best_season=None, keyword=None, max_height_m=None,
                      min_height_m=None, unesco_only=False, surf_break=None,
                      free_entry=False, limit=10):
    # WHERE clause only gets whatever filter was actually passed
    clauses = []
    params = {}
    params["limit"] = limit

    if category:
        clauses.append("category = :category")
        params["category"] = category
    if district:
        # some districts stored like "Southern/Uva" so we just match contains
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
    if len(clauses) > 0:
        where = "WHERE " + " AND ".join(clauses)

    sql = "SELECT * FROM attractions_full " + where + " ORDER BY name LIMIT :limit"
    rows = fetch_all(sql, params)

    cleaned = []
    for row in rows:
        cleaned.append(clean_row(row))
    return attach_images(cleaned)


def get_by_ids(ids):
    # takes ids we got from vector search and turns them back to full rows keeps same order
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
    # this is for the dropdowns we read it from data so it dont go out of date
    districts = fetch_all(
        "SELECT DISTINCT district FROM attractions "
        "WHERE district IS NOT NULL ORDER BY district"
    )

    names = []
    for row in districts:
        names.append(row["district"])

    return {
        "categories": ["beach", "mountain", "national_park", "historical_site"],
        "districts": names,
        "accessibility": ["easy", "moderate", "difficult"],
    }
