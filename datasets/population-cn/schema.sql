PRAGMA foreign_keys = ON;

CREATE TABLE population_age_sex (
    code TEXT PRIMARY KEY,
    country_code TEXT NOT NULL CHECK (country_code = 'CHN'),
    variant TEXT NOT NULL CHECK (variant = 'Medium'),
    year INTEGER NOT NULL CHECK (year BETWEEN 1900 AND 2200),
    mid_period REAL NOT NULL,
    age_group TEXT NOT NULL,
    age_start INTEGER NOT NULL CHECK (age_start >= 0),
    age_end INTEGER CHECK (age_end >= age_start),
    male_population INTEGER NOT NULL CHECK (male_population >= 0),
    female_population INTEGER NOT NULL CHECK (female_population >= 0),
    total_population INTEGER NOT NULL CHECK (total_population >= 0),
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 2),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    UNIQUE (country_code, variant, year, age_start),
    CHECK (abs(male_population + female_population - total_population) <= 2)
);

CREATE INDEX population_age_sex_year_idx
    ON population_age_sex(year, age_start);
