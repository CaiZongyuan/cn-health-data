PRAGMA foreign_keys = ON;

CREATE TABLE laboratory_test (
    code TEXT PRIMARY KEY CHECK (length(code) = 8),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    analyte TEXT NOT NULL,
    specimen TEXT NOT NULL,
    scale TEXT NOT NULL,
    result_kind TEXT NOT NULL CHECK (result_kind IN ('quantity', 'qualitative', 'ordinal', 'named')),
    unit_display TEXT,
    unit_ucum TEXT,
    precision INTEGER NOT NULL CHECK (precision BETWEEN 0 AND 4),
    healthy_strategy TEXT NOT NULL CHECK (healthy_strategy IN ('uniform', 'fixed-normal')),
    loinc_code TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
    source_version TEXT NOT NULL,
    CHECK ((result_kind = 'quantity') = (unit_display IS NOT NULL)),
    CHECK ((result_kind = 'quantity') = (unit_ucum IS NOT NULL)),
    CHECK ((result_kind = 'quantity') = (healthy_strategy = 'uniform'))
);

CREATE TABLE laboratory_reference (
    test_code TEXT NOT NULL REFERENCES laboratory_test(code),
    sex TEXT NOT NULL CHECK (sex IN ('all', 'male', 'female')),
    reference_kind TEXT NOT NULL CHECK (
        reference_kind IN ('range', 'upper-bound', 'lower-bound', 'coded', 'ordinal')
    ),
    low_value REAL,
    high_value REAL,
    normal_value TEXT,
    simulation_low REAL,
    simulation_high REAL,
    source_type TEXT NOT NULL CHECK (source_type IN ('national-standard', 'project-curated')),
    source_standard TEXT NOT NULL,
    source_version TEXT NOT NULL,
    source_location TEXT NOT NULL,
    notes TEXT NOT NULL,
    PRIMARY KEY (test_code, sex),
    CHECK (reference_kind != 'range' OR (low_value IS NOT NULL AND high_value IS NOT NULL AND low_value < high_value)),
    CHECK (reference_kind != 'upper-bound' OR (low_value IS NULL AND high_value IS NOT NULL)),
    CHECK (reference_kind != 'lower-bound' OR (low_value IS NOT NULL AND high_value IS NULL)),
    CHECK (reference_kind NOT IN ('coded', 'ordinal') OR normal_value IS NOT NULL),
    CHECK ((simulation_low IS NULL) = (simulation_high IS NULL)),
    CHECK (simulation_low IS NULL OR simulation_low < simulation_high)
);

CREATE TABLE laboratory_panel (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    specimen TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
    source_type TEXT NOT NULL CHECK (source_type = 'project-authored'),
    source_location TEXT NOT NULL,
    notes TEXT NOT NULL
);

CREATE TABLE laboratory_panel_member (
    panel_code TEXT NOT NULL REFERENCES laboratory_panel(code),
    test_code TEXT NOT NULL REFERENCES laboratory_test(code),
    sort_order INTEGER NOT NULL CHECK (sort_order > 0),
    PRIMARY KEY (panel_code, test_code),
    UNIQUE (panel_code, sort_order)
);

CREATE INDEX laboratory_test_category_idx ON laboratory_test(category, code);
CREATE INDEX laboratory_reference_test_idx ON laboratory_reference(test_code, sex);
CREATE INDEX laboratory_panel_member_test_idx ON laboratory_panel_member(test_code, panel_code);

CREATE VIRTUAL TABLE laboratory_test_fts USING fts5(
    name,
    analyte,
    category,
    content = 'laboratory_test',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE TABLE laboratory_test_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES laboratory_test(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;

CREATE VIRTUAL TABLE laboratory_panel_fts USING fts5(
    name,
    content = 'laboratory_panel',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE TABLE laboratory_panel_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES laboratory_panel(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;
