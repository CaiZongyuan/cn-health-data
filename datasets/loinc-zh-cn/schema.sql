PRAGMA foreign_keys = ON;

CREATE TABLE loinc (
    code TEXT PRIMARY KEY,
    component TEXT,
    property TEXT,
    time_aspect TEXT,
    system TEXT,
    scale_type TEXT,
    method_type TEXT,
    long_common_name TEXT NOT NULL,
    status TEXT,
    zh_display TEXT,
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64)
);

CREATE VIRTUAL TABLE loinc_fts USING fts5(
    long_common_name,
    zh_display,
    content = 'loinc',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE TABLE loinc_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES loinc(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;
