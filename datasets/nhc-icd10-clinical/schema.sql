PRAGMA foreign_keys = ON;

CREATE TABLE diagnosis (
    code TEXT PRIMARY KEY,
    main_code TEXT,
    additional_code TEXT,
    name TEXT NOT NULL,
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 2),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    CHECK (main_code IS NOT NULL OR additional_code IS NOT NULL),
    CHECK (code = COALESCE(main_code, additional_code))
);

CREATE INDEX diagnosis_main_code_idx ON diagnosis(main_code);
CREATE INDEX diagnosis_additional_code_idx ON diagnosis(additional_code);

CREATE VIRTUAL TABLE diagnosis_fts USING fts5(
    name,
    content = 'diagnosis',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE TABLE diagnosis_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES diagnosis(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;
