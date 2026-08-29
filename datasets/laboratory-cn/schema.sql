PRAGMA foreign_keys = ON;

CREATE TABLE laboratory_concept (
    code TEXT PRIMARY KEY,
    system TEXT NOT NULL CHECK (system = 'http://loinc.org'),
    terminology_version TEXT NOT NULL,
    display_zh TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('chemistry', 'hematology', 'vital-sign')),
    specimen TEXT NOT NULL CHECK (specimen IN ('blood', 'body')),
    result_type TEXT NOT NULL CHECK (result_type IN ('panel', 'quantity')),
    ucum_unit TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
    source_note TEXT NOT NULL,
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 2),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    CHECK ((result_type = 'panel') = (ucum_unit IS NULL))
);

CREATE INDEX laboratory_concept_category_idx
    ON laboratory_concept(category, code);

CREATE VIRTUAL TABLE laboratory_concept_fts USING fts5(
    display_zh,
    content = 'laboratory_concept',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE TABLE laboratory_concept_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES laboratory_concept(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;
