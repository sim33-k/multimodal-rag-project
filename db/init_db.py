import csv
import sys
from pathlib import Path

# python does not know where db.py is. We manually tell python to search the projects root directory for imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from db.connection import PROJECT_ROOT, get_engine

RAW_DIR = PROJECT_ROOT / "data" / "raw"
IMAGE_DIR = PROJECT_ROOT / "data" / "images"
SCHEMA_FILE = Path(__file__).with_name("schema.sql")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# attraction columns
CORE_COLUMNS = ["id","name","location","district","latitude","longitude","entrance_fee","accessibility","best_season",]

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

sql = SCHEMA_FILE.read_text(encoding="utf-8")
with get_engine().begin() as conn:
    conn.execute(text(sql))
print("Schema is now created.")

total = 0
with get_engine().begin() as conn:
    for filename in CATEGORIES:
        config = CATEGORIES[filename]
        csv_path = RAW_DIR / filename
        if not csv_path.exists():
            print("  skipping " + filename + " (not found)")
            continue

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
        placeholder_list = []
        for c in detail_cols:
            placeholder_list.append(":" + c)
        placeholders = ", ".join(placeholder_list)
        detail_sql = text(
            "INSERT INTO " + config["detail_table"] +
            " (attraction_id, " + ", ".join(detail_cols) + ")" +
            " VALUES (:attraction_id, " + placeholders + ")" +
            " ON CONFLICT (attraction_id) DO NOTHING"
        )

        for row in rows:
            # empty cells should be will be NULL
            core = {}
            for col in CORE_COLUMNS:
                value = row.get(col)
                if value is not None:
                    value = value.strip()
                    if value == "":
                        value = None
                core[col] = value

            for col in ("latitude", "longitude"):
                value = core[col]
                if value is not None:
                    try:
                        value = float(value)
                    except ValueError:
                        value = None
                core[col] = value

            core["category"] = config["category"]
            conn.execute(core_sql, core)

            detail = {"attraction_id": row["id"].strip()}
            for col in detail_cols:
                value = row.get(col)
                if value is not None:
                    value = value.strip()
                    if value == "":
                        value = None

                if col in config["boolean_columns"]:
                    if value is not None:
                        value = value.lower() in ["true", "yes", "1", "y"]
                elif col in config["numeric_columns"]:
                    if value is not None:
                        try:
                            value = float(value)
                        except ValueError:
                            value = None

                detail[col] = value
            conn.execute(detail_sql, detail)

        total = total + len(rows)
        print("  " + filename + ": " + str(len(rows)) + " rows")

    # Matching image files to attractions by filename
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
            # taking the longest match
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

    print("  reg " + str(inserted) + " images")

print("Done. " + str(total) + " attractions are now loaded!!!!")
