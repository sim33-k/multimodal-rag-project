# Creates the tables and loads the CSVs into them.
# The CSVs are flat (one row = one attraction) because that's easier to edit in
# Excel, so this script has to split each row into the main table + the detail
# table for that category.
#
# Run:  python -m db.init_db

import csv
import sys
from pathlib import Path

from sqlalchemy import text

from db.connection import PROJECT_ROOT, get_engine

RAW_DIR = PROJECT_ROOT / "data" / "raw"
IMAGE_DIR = PROJECT_ROOT / "data" / "images"
SCHEMA_FILE = Path(__file__).with_name("schema.sql")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# columns that every attraction has, in CSV order
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

# One entry per CSV file. If we ever add a 5th category we just add it here and
# add the table in schema.sql.
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


def clean(value):
    # empty cells should be NULL, not ""
    if value is None:
        return None
    value = value.strip()
    if value == "":
        return None
    return value


def to_float(value):
    value = clean(value)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_bool(value):
    value = clean(value)
    if value is None:
        return None
    return value.lower() in ["true", "yes", "1", "y"]


def create_schema():
    # schema.sql drops everything first, so running this again is a full reset
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    with get_engine().begin() as conn:
        conn.execute(text(sql))
    print("Schema created.")


def load_category(conn, filename, config):
    csv_path = RAW_DIR / filename
    if not csv_path.exists():
        print("  skipping " + filename + " (not found)")
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
    placeholders = ", ".join(":" + c for c in detail_cols)
    detail_sql = text(
        "INSERT INTO " + config["detail_table"] +
        " (attraction_id, " + ", ".join(detail_cols) + ")" +
        " VALUES (:attraction_id, " + placeholders + ")" +
        " ON CONFLICT (attraction_id) DO NOTHING"
    )

    for row in rows:
        core = {}
        for col in CORE_COLUMNS:
            core[col] = clean(row.get(col))
        core["latitude"] = to_float(row.get("latitude"))
        core["longitude"] = to_float(row.get("longitude"))
        core["category"] = config["category"]
        conn.execute(core_sql, core)

        detail = {"attraction_id": row["id"].strip()}
        for col in detail_cols:
            raw = row.get(col)
            if col in config["boolean_columns"]:
                detail[col] = to_bool(raw)
            elif col in config["numeric_columns"]:
                detail[col] = to_float(raw)
            else:
                detail[col] = clean(raw)
        conn.execute(detail_sql, detail)

    print("  " + filename + ": " + str(len(rows)) + " rows")
    return len(rows)


def load_images(conn):
    # Match image files to attractions by filename, e.g. sigiriya.jpg and
    # sigiriya_2.jpg both belong to sigiriya.
    known_ids = set()
    for row in conn.execute(text("SELECT id FROM attractions")).fetchall():
        known_ids.add(row[0])

    inserted = 0

    for config in CATEGORIES.values():
        folder = IMAGE_DIR / config["image_folder"]
        if not folder.exists():
            continue

        for image_path in sorted(folder.iterdir()):
            if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            stem = image_path.stem
            matches = []
            for aid in known_ids:
                if stem == aid or stem.startswith(aid + "_"):
                    matches.append(aid)
            if len(matches) == 0:
                print("  no attraction matches image: " + image_path.name)
                continue
            # take the longest match, otherwise little_adams_peak.jpg gets
            # matched to adams_peak
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
            inserted = inserted + 1

    print("  registered " + str(inserted) + " images")
    return inserted


def main():
    create_schema()

    print("Loading CSVs...")
    total = 0
    with get_engine().begin() as conn:
        for filename in CATEGORIES:
            total = total + load_category(conn, filename, CATEGORIES[filename])
        load_images(conn)

    print("Done. " + str(total) + " attractions loaded.")


if __name__ == "__main__":
    sys.exit(main())
