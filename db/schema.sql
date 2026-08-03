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


CREATE TABLE images (
    image_id SERIAL PRIMARY KEY,
    attraction_id TEXT NOT NULL REFERENCES attractions(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    caption TEXT
);

CREATE INDEX idx_attractions_category ON attractions(category);
CREATE INDEX idx_attractions_district ON attractions(district);
CREATE INDEX idx_images_attraction ON images(attraction_id);

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


ALTER TABLE attractions ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english',
            name || ' ' || coalesce(location, '') || ' ' || coalesce(district, ''))
    ) STORED;

CREATE INDEX idx_attractions_search ON attractions USING GIN (search_vector);
