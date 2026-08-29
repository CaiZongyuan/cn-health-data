PRAGMA foreign_keys = ON;

CREATE TABLE administrative_division (
    code TEXT PRIMARY KEY,
    parent_code TEXT REFERENCES administrative_division(code),
    level INTEGER NOT NULL CHECK (level BETWEEN 0 AND 2),
    name_zh TEXT NOT NULL,
    short_name_zh TEXT NOT NULL,
    pinyin TEXT NOT NULL,
    pinyin_prefix TEXT NOT NULL,
    external_code TEXT NOT NULL UNIQUE CHECK (length(external_code) = 12),
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 2),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64)
);

CREATE INDEX administrative_division_parent_idx
    ON administrative_division(parent_code, level);

CREATE TABLE place (
    code TEXT PRIMARY KEY,
    geoname_id INTEGER NOT NULL UNIQUE,
    name_zh TEXT NOT NULL,
    name_ascii TEXT NOT NULL,
    alternate_names_zh TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('administrative-division', 'populated-place')),
    feature_code TEXT NOT NULL,
    country_code TEXT NOT NULL CHECK (country_code = 'CN'),
    admin1_code TEXT NOT NULL,
    admin2_code TEXT NOT NULL,
    admin3_code TEXT NOT NULL,
    admin4_code TEXT NOT NULL,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    population INTEGER NOT NULL CHECK (population >= 0),
    timezone TEXT NOT NULL,
    modified_on TEXT NOT NULL CHECK (modified_on GLOB '????-??-??'),
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 1),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64)
);

CREATE INDEX place_admin_codes_idx
    ON place(admin1_code, admin2_code, admin3_code, admin4_code);
CREATE INDEX place_population_idx ON place(kind, population DESC);

CREATE VIRTUAL TABLE place_fts USING fts5(
    name_zh,
    name_ascii,
    alternate_names_zh,
    content = 'place',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE VIEW populated_place AS
SELECT * FROM place WHERE kind = 'populated-place';

CREATE TABLE postal_area (
    code TEXT PRIMARY KEY,
    postal_code TEXT NOT NULL,
    place_name TEXT NOT NULL,
    admin1_name TEXT NOT NULL,
    admin1_code TEXT NOT NULL,
    admin2_name TEXT NOT NULL,
    admin2_code TEXT NOT NULL,
    admin3_name TEXT NOT NULL,
    admin3_code TEXT NOT NULL,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    accuracy INTEGER CHECK (accuracy BETWEEN 1 AND 6),
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 1),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64)
);

CREATE INDEX postal_area_code_idx ON postal_area(postal_code);
CREATE INDEX postal_area_admin_idx
    ON postal_area(admin1_code, admin2_code, admin3_code);
