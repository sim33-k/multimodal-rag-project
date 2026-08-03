"""Create the schema and load the CSVs into Postgres.

The CSVs are kept flat so they stay easy to edit by hand in a spreadsheet. This
script is what turns each flat row into the normalised form: the shared columns
go to `attractions`, the category-specific columns go to that category's detail
table, and any matching files under data/images/ are registered in `images`.

Run with:  python -m db.init_db
"""

import csv
import sys
from pathlib import Path

from sqlalchemy import text

from db.connection import PROJECT_ROOT, get_engine

RAW_DIR = PROJECT_ROOT / "data" / "raw"
IMAGE_DIR = PROJECT_ROOT / "data" / "images"
SCHEMA_FILE = Path(__file__).with_name("schema.sql")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Columns every attraction shares, in the order they appear in the CSVs.
CORE_COLUMNS = [
    "id",
    "name",
    "location",
    "district",
    "latitude",
    "longitude",
    "entrance_fee",
    "accessibility",
    "best_season",
]

# Maps each CSV to its category value, its detail table, that table's columns,
# and the image subfolder. Adding a fifth category means adding one entry here
# plus a detail table in schema.sql - nothing else in the loader changes.
CATEGORIES = {
    "beaches.csv": {
        "category": "beach",
        "detail_table": "beach_details",
        "detail_columns": ["activity_type", "water_quality", "surf_break"],
        "image_folder": "beaches",
        "boolean_columns": {"surf_break"},
        "numeric_columns": set(),
    },
    "mountains.csv": {
        "category": "mountain",
        "detail_table": "mountain_details",
        "detail_columns": ["height_m", "trekking_difficulty", "duration_hours"],
        "image_folder": "mountains",
        "boolean_columns": set(),
        "numeric_columns": {"height_m", "duration_hours"},
    },
    "national_parks.csv": {
        "category": "national_park",
        "detail_table": "national_park_details",
        "detail_columns": [
            "conservation_status",
            "habitat",
            "area_sq_km",
            "notable_wildlife",
        ],
        "image_folder": "national_parks",
        "boolean_columns": set(),
        "numeric_columns": {"area_sq_km"},
    },
    "historical_sites.csv": {
        "category": "historical_site",
        "detail_table": "historical_site_details",
        "detail_columns": [
            "historical_period",
            "architectural_style",
            "unesco_status",
        ],
        "image_folder": "historical_sites",
        "boolean_columns": set(),
        "numeric_columns": set(),
    },
}


def _clean(value: str | None) -> str | None:
    """Blank cells become NULL rather than empty strings."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _to_float(value: str | None) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _to_bool(value: str | None) -> bool | None:
    value = _clean(value)
    if value is None:
        return None
    return value.lower() in {"true", "yes", "1", "y"}


def create_schema() -> None:
    """Run schema.sql. It drops existing objects first, so this is a full reset."""
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with get_engine().begin() as conn:
        conn.execute(text(sql))
    print("Schema created.")


def load_category(conn, filename: str, config: dict) -> int:
    csv_path = RAW_DIR / filename
    if not csv_path.exists():
        print(f"  skipping {filename} (not found)")
        return 0

    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    core_sql = text(
        """
        INSERT INTO attractions
            (id, name, category, location, district, latitude, longitude,
             entrance_fee, accessibility, best_season)
        VALUES
            (:id, :name, :category, :location, :district, :latitude, :longitude,
             :entrance_fee, :accessibility, :best_season)
        ON CONFLICT (id) DO NOTHING
        """
    )

    detail_cols = config["detail_columns"]
    detail_sql = text(
        f"""
        INSERT INTO {config['detail_table']}
            (attraction_id, {', '.join(detail_cols)})
        VALUES
            (:attraction_id, {', '.join(f':{c}' for c in detail_cols)})
        ON CONFLICT (attraction_id) DO NOTHING
        """
    )

    for row in rows:
        core = {col: _clean(row.get(col)) for col in CORE_COLUMNS}
        core["latitude"] = _to_float(row.get("latitude"))
        core["longitude"] = _to_float(row.get("longitude"))
        core["category"] = config["category"]
        conn.execute(core_sql, core)

        detail = {"attraction_id": row["id"].strip()}
        for col in detail_cols:
            raw = row.get(col)
            if col in config["boolean_columns"]:
                detail[col] = _to_bool(raw)
            elif col in config["numeric_columns"]:
                detail[col] = _to_float(raw)
            else:
                detail[col] = _clean(raw)
        conn.execute(detail_sql, detail)

    print(f"  {filename}: {len(rows)} rows")
    return len(rows)


def load_images(conn) -> int:
    """Register image files by matching filenames against attraction ids.

    Convention from the spec: a file is linked to an attraction when its name is
    the attraction id, optionally followed by a suffix, e.g. sigiriya.jpg and
    sigiriya_2.jpg both belong to `sigiriya`. Paths are stored relative to the
    project root so they stay valid on both members' machines.
    """
    known_ids = {
        row[0] for row in conn.execute(text("SELECT id FROM attractions")).fetchall()
    }
    inserted = 0

    for config in CATEGORIES.values():
        folder = IMAGE_DIR / config["image_folder"]
        if not folder.exists():
            continue

        for image_path in sorted(folder.iterdir()):
            if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            stem = image_path.stem
            # Longest match wins so `little_adams_peak` is not claimed by `adams_peak`.
            matches = [aid for aid in known_ids if stem == aid or stem.startswith(aid + "_")]
            if not matches:
                print(f"  unmatched image (no attraction with that id): {image_path.name}")
                continue
            attraction_id = max(matches, key=len)

            relative = image_path.relative_to(PROJECT_ROOT).as_posix()
            conn.execute(
                text(
                    """
                    INSERT INTO images (attraction_id, file_path, caption)
                    SELECT :attraction_id, :file_path, :caption
                    WHERE NOT EXISTS (
                        SELECT 1 FROM images WHERE file_path = :file_path
                    )
                    """
                ),
                {
                    "attraction_id": attraction_id,
                    "file_path": relative,
                    "caption": None,
                },
            )
            inserted += 1

    print(f"  registered {inserted} images")
    return inserted


def main() -> None:
    create_schema()

    print("Loading CSVs...")
    total = 0
    with get_engine().begin() as conn:
        for filename, config in CATEGORIES.items():
            total += load_category(conn, filename, config)
        load_images(conn)

    print(f"Done. {total} attractions loaded.")


if __name__ == "__main__":
    sys.exit(main())
