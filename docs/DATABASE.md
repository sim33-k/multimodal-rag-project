# Database design

## The modelling problem

Four categories of attraction share some fields and differ in others.

| | Beach | Mountain | National park | Historical site |
|---|---|---|---|---|
| name, district, coordinates, fee, season | ✓ | ✓ | ✓ | ✓ |
| activity type, water quality, surf break | ✓ | | | |
| height, trekking difficulty, duration | | ✓ | | |
| conservation status, habitat, area, wildlife | | | ✓ | |
| period, architectural style, UNESCO status | | | | ✓ |

The obvious approach — one wide `attractions` table with every column — produces
a **sparse table**. A beach row carries eleven permanently NULL columns, and the
NULLs are structural rather than "unknown", so `height_m IS NULL` cannot
distinguish "this is not a mountain" from "we have not measured it". Adding a
fifth category widens every existing row.

## The chosen pattern

**Class-table inheritance** (supertype/subtype): one core table holding what all
attractions share, plus one detail table per category holding only that category's
fields, joined 1:1.

```
                    ┌─────────────────┐
                    │   attractions   │  id, name, category, location,
                    │   (supertype)   │  district, lat, lon, fee,
                    └────────┬────────┘  accessibility, best_season
                             │ 1:1
     ┌───────────────┬───────┴───────┬─────────────────┐
     ▼               ▼               ▼                 ▼
beach_details  mountain_details  national_park_  historical_site_
                                    details          details

                    ┌─────────────────┐
                    │     images      │  1:N from attractions
                    └─────────────────┘
```

Each detail table's primary key **is** its foreign key:

```sql
CREATE TABLE beach_details (
    attraction_id TEXT PRIMARY KEY REFERENCES attractions(id) ON DELETE CASCADE,
    activity_type TEXT,
    water_quality TEXT,
    surf_break BOOLEAN
);
```

That single declaration does three jobs: it enforces the 1:1 cardinality (a
primary key cannot repeat), it guarantees referential integrity, and `ON DELETE
CASCADE` means removing an attraction cleans up its details automatically.

### What this buys

- No structural NULLs. A row exists in `beach_details` only if it is a beach.
- Category-specific constraints are possible. `height_m` can be made `NOT NULL`
  on mountains without affecting beaches.
- A fifth category is a new table, not a schema migration on existing rows.

### What it costs

Every read needs joins. Which is why the view exists.

## The flattening view

```sql
CREATE VIEW attractions_full AS
SELECT a.*,
       b.activity_type, b.water_quality, b.surf_break,
       m.height_m, m.trekking_difficulty, m.duration_hours,
       np.conservation_status, np.habitat, np.area_sq_km, np.notable_wildlife,
       h.historical_period, h.architectural_style, h.unesco_status
FROM attractions a
LEFT JOIN beach_details b            ON a.id = b.attraction_id
LEFT JOIN mountain_details m         ON a.id = m.attraction_id
LEFT JOIN national_park_details np   ON a.id = np.attraction_id
LEFT JOIN historical_site_details h  ON a.id = h.attraction_id;
```

Application code selects from `attractions_full` and never writes these joins by
hand. The normalisation benefit is kept at the storage layer while queries stay
as simple as they would be against a wide table.

The view does reintroduce NULLs in its output — a beach row has NULL `height_m`.
Those are stripped in `retrieval/sql_query.py:clean_row()` before results leave
the retrieval layer, using a per-category allowlist. The important difference is
that the NULLs are a presentation artefact of the view, not stored data.

## Full-text search

```sql
ALTER TABLE attractions ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english',
            name || ' ' || coalesce(location,'') || ' ' || coalesce(district,''))
    ) STORED;

CREATE INDEX idx_attractions_search ON attractions USING GIN (search_vector);
```

A **generated column** rather than a trigger: Postgres keeps it in sync on every
insert and update with no maintenance code and no chance of the two drifting.
`coalesce` is required because `NULL` would propagate through the concatenation
and blank the whole vector for any attraction missing a location.

The GIN index is what makes `@@` matching fast; without it Postgres would scan
every row and recompute nothing — the vector is stored, but the lookup would
still be linear.

### Query strategy

`retrieval/fulltext_search.py` runs two passes:

1. `websearch_to_tsquery` — requires every term to be present. Precise, and the
   right behaviour for a query like `Sigiriya`.
2. If that returns nothing, an OR of the individual terms via `to_tsquery`.

The second pass exists because conversational queries ("ancient rock fortress
near Matale") almost never have every term present in a name or district, so the
strict match returns an empty set. Falling back to OR surfaces partial matches and
lets `ts_rank` order them.

## Indexes

| Index | Column | Why |
|---|---|---|
| `idx_attractions_category` | `category` | Filtered on in nearly every structured query |
| `idx_attractions_district` | `district` | The second most common filter |
| `idx_images_attraction` | `images.attraction_id` | Batched image lookup per result set |
| `idx_attractions_search` | `search_vector` (GIN) | Full-text matching |

At 40 rows these are not load-bearing — Postgres will sequential-scan a table this
small regardless. They are declared because they express the intended access
pattern and would matter at realistic scale.

## Constraints

```sql
category TEXT NOT NULL CHECK (category IN
    ('beach','mountain','national_park','historical_site'))
accessibility TEXT CHECK (accessibility IN ('easy','moderate','difficult'))
```

`CHECK` constraints rather than application-level validation, so a bad CSV row
fails at import rather than surfacing as a broken filter later. `accessibility`
is nullable — unknown is a legitimate state — but if present it must be one of
the three values the sidebar offers.

## Loading

CSVs are kept flat, one file per category, because they are edited by hand in a
spreadsheet. `db/init_db.py` is what turns a flat row into the normalised form:

```
beaches.csv row
    ├─ core columns  ──▶ attractions      (with category='beach')
    └─ detail columns ─▶ beach_details
```

The category configuration lives in one dictionary at the top of the loader,
listing each CSV's category value, detail table, columns, and which of those
columns need boolean or numeric coercion. Adding a category means one entry there
and one table in `schema.sql`.

`schema.sql` drops all objects before recreating them, so `init_db.py` is a full
reset and can be re-run freely after a CSV edit.

Images are registered separately by matching filenames against attraction ids —
`sigiriya.jpg` and `sigiriya_2.jpg` both belong to `sigiriya`. The match takes the
**longest** candidate id so that `little_adams_peak.jpg` is not claimed by
`adams_peak`.
