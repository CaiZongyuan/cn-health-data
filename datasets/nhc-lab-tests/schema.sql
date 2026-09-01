PRAGMA foreign_keys = ON;

CREATE TABLE laboratory_test (
    code TEXT PRIMARY KEY CHECK (length(code) = 8),
    name TEXT NOT NULL,
    category_code TEXT NOT NULL CHECK (length(category_code) = 2),
    category_name TEXT NOT NULL,
    analyte TEXT NOT NULL,
    specimen_code TEXT NOT NULL CHECK (length(specimen_code) = 2),
    specimen_name TEXT NOT NULL,
    scale_code TEXT NOT NULL CHECK (length(scale_code) = 1),
    scale_name TEXT NOT NULL,
    source_standard TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_location TEXT NOT NULL,
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row BETWEEN 1 AND 399),
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    CHECK (code = category_code || substr(code, 3, 3) || specimen_code || scale_code)
);

CREATE INDEX laboratory_test_category_idx ON laboratory_test(category_code, code);
CREATE INDEX laboratory_test_specimen_idx ON laboratory_test(specimen_code, code);
CREATE INDEX laboratory_test_scale_idx ON laboratory_test(scale_code, code);

CREATE VIRTUAL TABLE laboratory_test_fts USING fts5(
    name,
    analyte,
    category_name,
    content = 'laboratory_test',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE TABLE laboratory_test_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES laboratory_test(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;
