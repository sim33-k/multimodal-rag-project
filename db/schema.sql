-- SL Tourism multimodal RAG - relational schema
--
-- Design note: a single wide `attractions` table holding every category's columns
-- would leave most fields NULL on any given row (a sparse-table anti-pattern).
-- Instead this uses the supertype/subtype pattern, also known as class-table
-- inheritance: one core table with the fields every attraction shares, plus one
-- detail table per category joined 1:1 on attraction_id. The attractions_full
-- view flattens them back out so application code never hand-writes the joins.

-- Dropped in dependency order so this script can be re-run against an existing
-- database during development.
DROP VIEW IF EXISTS attractions_full;
DROP TABLE IF EXISTS images CASCADE;
DROP TABLE IF EXISTS beach_details CASCADE;
DROP TABLE IF EXISTS mountain_details CASCADE;
DROP TABLE IF EXISTS national_park_details CASCADE;
DROP TABLE IF EXISTS historical_site_details CASCADE;
DROP TABLE IF EXISTS attractions CASCADE;

-- Core table: fields common to all four categories.
CREATE TABLE attractions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('beach','mountain','national_park','historical_site')),
    location TEXT,
    district TEXT,
    latitude REAL,
    longitude REAL,
    entrance_fee TEXT,
    accessibility TEXT CHECK (accessibility IN ('easy','moderate','difficult')),
    best_season TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Subtype tables. The primary key is also the foreign key, which enforces the
-- 1:1 relationship: an attraction can have at most one detail row per category.
CREATE TABLE beach_details (
    attraction_id TEXT PRIMARY KEY REFERENCES attractions(id) ON DELETE CASCADE,
    activity_type TEXT,
    water_quality TEXT,
    surf_break BOOLEAN
);

CREATE TABLE mountain_details (
    attraction_id TEXT PRIMARY KEY REFERENCES attractions(id) ON DELETE CASCADE,
    height_m REAL,
    trekking_difficulty TEXT,
    duration_hours REAL
);

CREATE TABLE national_park_details (
    attraction_id TEXT PRIMARY KEY REFERENCES attractions(id) ON DELETE CASCADE,
    conservation_status TEXT,
    habitat TEXT,
    area_sq_km REAL,
    notable_wildlife TEXT
);

CREATE TABLE historical_site_details (
    attraction_id TEXT PRIMARY KEY REFERENCES attractions(id) ON DELETE CASCADE,
    historical_period TEXT,
    architectural_style TEXT,
    unesco_status TEXT
);

-- One attraction may have several images, so this is a plain 1:N table rather
-- than a column on attractions.
CREATE TABLE images (
    image_id SERIAL PRIMARY KEY,
    attraction_id TEXT NOT NULL REFERENCES attractions(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    caption TEXT
);

-- Indexes on the columns the structured filters actually use.
CREATE INDEX idx_attractions_category ON attractions(category);
CREATE INDEX idx_attractions_district ON attractions(district);
CREATE INDEX idx_images_attraction ON images(attraction_id);

-- Flattening view: application code SELECTs from here, never hand-writes the JOINs.
-- Columns from non-matching categories come back NULL, which is exactly what the
-- serialisation layer strips out before returning a row.
CREATE VIEW attractions_full AS
SELECT
    a.*,
    b.activity_type, b.water_quality, b.surf_break,
    m.height_m, m.trekking_difficulty, m.duration_hours,
    np.conservation_status, np.habitat, np.area_sq_km, np.notable_wildlife,
    h.historical_period, h.architectural_style, h.unesco_status
FROM attractions a
LEFT JOIN beach_details b ON a.id = b.attraction_id
LEFT JOIN mountain_details m ON a.id = m.attraction_id
LEFT JOIN national_park_details np ON a.id = np.attraction_id
LEFT JOIN historical_site_details h ON a.id = h.attraction_id;

-- Postgres-native full-text search. This is deliberately separate from the
-- ChromaDB semantic search: lexical matching catches exact proper nouns
-- ("Sigiriya", "Matale") that dense embeddings often blur together, while
-- embeddings catch paraphrase that lexical matching misses entirely.
-- The generated column keeps the vector in sync with no trigger to maintain.
ALTER TABLE attractions ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english',
            name || ' ' || coalesce(location, '') || ' ' || coalesce(district, ''))
    ) STORED;

CREATE INDEX idx_attractions_search ON attractions USING GIN (search_vector);
