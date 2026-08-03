-- Tables for the tourism search project.
--
-- We didn't put everything in one big attractions table because most of the
-- columns would be empty on most rows - a beach has no height, a mountain has
-- no water quality. So there's one main table with the stuff every attraction
-- has, and a separate small table per category for the rest. The view at the
-- bottom sticks them back together so the Python code doesn't have to write
-- the joins every time.

-- drop first so this file can just be re-run when we change something.
-- order matters, the detail tables point at attractions.
DROP VIEW IF EXISTS attractions_full;
DROP TABLE IF EXISTS images CASCADE;
DROP TABLE IF EXISTS beach_details CASCADE;
DROP TABLE IF EXISTS mountain_details CASCADE;
DROP TABLE IF EXISTS national_park_details CASCADE;
DROP TABLE IF EXISTS historical_site_details CASCADE;
DROP TABLE IF EXISTS attractions CASCADE;

-- the main table - everything that all 4 categories have
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

-- One detail table per category. attraction_id is the primary key AND the
-- foreign key, which is a neat trick - because a primary key can't repeat, you
-- automatically get one detail row per attraction and nothing more.
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

-- separate table because some places have more than one photo
CREATE TABLE images (
    image_id SERIAL PRIMARY KEY,
    attraction_id TEXT NOT NULL REFERENCES attractions(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    caption TEXT
);

-- the columns we actually filter on
CREATE INDEX idx_attractions_category ON attractions(category);
CREATE INDEX idx_attractions_district ON attractions(district);
CREATE INDEX idx_images_attraction ON images(attraction_id);

-- This is what the Python code queries, not the tables. LEFT JOIN so an
-- attraction still shows up even though only one of the four detail tables has
-- a row for it. The other three come back as NULL and get stripped out in
-- sql_query.py before the results go anywhere.
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

-- Postgres full text search, for keyword matching. This is a different thing to
-- the ChromaDB search - searching "Sigiriya" with embeddings also brings back
-- other rock fortresses, but a keyword match doesn't do that.
--
-- GENERATED means Postgres updates the column itself on every insert, so we
-- don't need a trigger. The coalesce calls are needed because if location is
-- NULL the whole thing concatenates to NULL and the row becomes unsearchable.
ALTER TABLE attractions ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english',
            name || ' ' || coalesce(location, '') || ' ' || coalesce(district, ''))
    ) STORED;

-- GIN index, otherwise the @@ match scans every row
CREATE INDEX idx_attractions_search ON attractions USING GIN (search_vector);
