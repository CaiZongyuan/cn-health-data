PRAGMA foreign_keys = ON;

CREATE TABLE drug (
    code TEXT PRIMARY KEY,
    data_source TEXT NOT NULL,
    registered_name TEXT NOT NULL,
    trade_name TEXT NOT NULL,
    registered_dosage_form TEXT NOT NULL,
    dosage_form TEXT NOT NULL,
    registered_specification TEXT NOT NULL,
    specification TEXT NOT NULL,
    packaging_material TEXT NOT NULL,
    minimum_package_quantity TEXT NOT NULL,
    minimum_dosage_unit TEXT NOT NULL,
    minimum_package_unit TEXT NOT NULL,
    drug_company TEXT NOT NULL,
    repackaging_company TEXT,
    manufacturer TEXT NOT NULL,
    approval_number TEXT NOT NULL,
    previous_approval_number TEXT,
    standard_drug_code TEXT NOT NULL,
    marketing_authorization_holder TEXT,
    market_status TEXT NOT NULL
        CHECK (market_status IN ('上市', '停产', '未上市')),
    insurance_name TEXT,
    reimbursement_class_2025 TEXT,
    insurance_dosage_form TEXT,
    insurance_number TEXT,
    note TEXT,
    former_code TEXT,
    source_row INTEGER NOT NULL UNIQUE CHECK (source_row >= 2),
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL CHECK (length(source_sha256) = 64)
);

CREATE INDEX drug_approval_number_idx ON drug(approval_number);
CREATE INDEX drug_standard_code_idx ON drug(standard_drug_code);

CREATE VIRTUAL TABLE drug_fts USING fts5(
    registered_name,
    trade_name,
    insurance_name,
    manufacturer,
    content = 'drug',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

CREATE TABLE drug_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES drug(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;
