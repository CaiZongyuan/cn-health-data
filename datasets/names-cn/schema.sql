PRAGMA foreign_keys = ON;

CREATE TABLE name_component (
    code TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('surname', 'given-name')),
    gender TEXT NOT NULL CHECK (gender IN ('any', 'female', 'male')),
    text TEXT NOT NULL,
    weight REAL NOT NULL CHECK (weight > 0),
    is_compound INTEGER NOT NULL CHECK (is_compound IN (0, 1)),
    source_duplicate INTEGER NOT NULL CHECK (source_duplicate IN (0, 1)),
    source_line INTEGER NOT NULL CHECK (source_line >= 1),
    source_ordinal INTEGER NOT NULL UNIQUE CHECK (source_ordinal >= 1),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    UNIQUE (kind, gender, text),
    CHECK (
        (kind = 'surname' AND gender = 'any')
        OR (kind = 'given-name' AND gender IN ('female', 'male'))
    )
);

CREATE INDEX name_component_selection_idx ON name_component(kind, gender, weight DESC);

CREATE VIEW surname AS
SELECT * FROM name_component WHERE kind = 'surname';

CREATE VIEW given_name AS
SELECT * FROM name_component WHERE kind = 'given-name';
