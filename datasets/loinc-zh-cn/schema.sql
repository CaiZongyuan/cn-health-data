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
    short_name TEXT,
    consumer_name TEXT,
    class TEXT,
    class_type INTEGER,
    order_obs TEXT,
    status TEXT NOT NULL,
    status_reason TEXT,
    status_text TEXT,
    change_type TEXT,
    definition_description TEXT,
    version_first_released TEXT,
    version_last_changed TEXT,
    panel_type TEXT,
    zh_display TEXT,
    source_metadata_json TEXT NOT NULL
        CHECK (json_valid(source_metadata_json) AND json_type(source_metadata_json) = 'object'),
    translation_metadata_json TEXT NOT NULL
        CHECK (json_valid(translation_metadata_json)
            AND json_type(translation_metadata_json) = 'object'),
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 2),
    translation_source_row INTEGER UNIQUE CHECK (translation_source_row >= 2),
    source_version TEXT NOT NULL,
    core_source_sha256 TEXT NOT NULL CHECK (length(core_source_sha256) = 64),
    translation_source_sha256 TEXT NOT NULL CHECK (length(translation_source_sha256) = 64)
);

CREATE INDEX loinc_class_idx ON loinc(class, status, code);
CREATE INDEX loinc_status_idx ON loinc(status, code);

CREATE TABLE loinc_unit (
    loinc_code TEXT NOT NULL REFERENCES loinc(code),
    ucum_unit TEXT NOT NULL,
    unit_kind TEXT NOT NULL,
    unit_ordinal INTEGER NOT NULL CHECK (unit_ordinal >= 1),
    source_member TEXT NOT NULL,
    source_row INTEGER NOT NULL CHECK (source_row >= 2),
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    PRIMARY KEY (loinc_code, unit_kind, source_member, source_row, unit_ordinal)
) WITHOUT ROWID;

CREATE INDEX loinc_unit_value_idx ON loinc_unit(ucum_unit, loinc_code);

CREATE TABLE loinc_specimen (
    loinc_code TEXT NOT NULL REFERENCES loinc(code),
    part_number TEXT NOT NULL,
    part_name TEXT NOT NULL,
    part_display_name TEXT,
    link_type TEXT NOT NULL,
    source_member TEXT NOT NULL,
    source_row INTEGER NOT NULL CHECK (source_row >= 2),
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    PRIMARY KEY (loinc_code, part_number, link_type)
) WITHOUT ROWID;

CREATE INDEX loinc_specimen_part_idx ON loinc_specimen(part_number, loinc_code);

CREATE TABLE loinc_panel_member (
    parent_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    panel_code TEXT NOT NULL REFERENCES loinc(code),
    member_code TEXT NOT NULL REFERENCES loinc(code),
    member_order INTEGER NOT NULL CHECK (member_order >= 0),
    relationship TEXT NOT NULL,
    source_metadata_json TEXT NOT NULL
        CHECK (json_valid(source_metadata_json) AND json_type(source_metadata_json) = 'object'),
    source_member TEXT NOT NULL,
    source_row INTEGER NOT NULL CHECK (source_row >= 2),
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64),
    PRIMARY KEY (parent_id, member_id),
    CHECK (panel_code <> member_code)
) WITHOUT ROWID;

CREATE INDEX loinc_panel_member_code_idx ON loinc_panel_member(member_code, panel_code);

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
