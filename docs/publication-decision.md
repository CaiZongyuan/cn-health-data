# Normalized Artifact Publication Decision

Reviewed by: CN Health Data maintainers  
Reviewed at: 2026-09-01  
Applies to: normalized SQLite/zstd and Parquet Releases listed below

## Decision

The maintainers elect to distribute the project's normalized, versioned runtime
and analytical projections for every implemented Dataset. Raw source files are
not distributed. Public Manifests retain source identity, version, hashes,
record counts, attribution, and source-specific notices.

This is a publisher and product decision, not a declaration that every source
is repository-owned or public domain. The repository MIT License applies only
to repository-authored software and original material. More specific source
terms and notices continue to apply to third-party content.

## Dataset Decisions

### `nhsa-drugs`

Publish the normalized code/reference projection from the pinned local workbook
snapshot. Preserve the distribution-source identity, original filename, data
date, worksheet, SHA256, and record count in the Manifest. Do not distribute the
source XLSX or research PDF and do not describe the source rows as
repository-authored.

### `nhc-icd10-clinical`

Publish the normalized clinical diagnosis code/name projection from the pinned
local workbook snapshot. Preserve the original authority identity, filename,
version, worksheet, SHA256, and record count. Do not distribute the source XLSX
or imply ownership of the underlying classification.

### `loinc-zh-cn`

Publish only artifact types allowed by the Dataset Contract. Preserve the LOINC
License 5.8, short license, attribution, LOINC version, official Chinese variant
identity, unchanged codes, and source-member provenance. The public artifact is
not relicensed under the repository MIT License.

### `geography-cn`

Publish the normalized composite projection while preserving source roles for
the pinned AreaCity collection and GeoNames gazetteer/postal data. Retain the
upstream commit/URLs and GeoNames attribution in the Manifest and documentation.

### `names-cn`

Publish the normalized, aggregate name components parsed from the pinned Faker
`zh_CN` provider. Preserve the Faker project identity, MIT source license,
upstream commit, and source URL. The Dataset contains no person-level records.

### `population-cn`

Publish the China aggregate age/sex projection from UN World Population
Prospects 2024. Preserve the UN Population Division attribution, WPP2024 Medium
variant, country code, source URL, and citation. The Dataset contains aggregate
statistics and no person-level records.

### `laboratory-cn`

Publish the normalized WS/T 886 adult runtime projection, project-authored
reference/simulation metadata, and hospital panels. Preserve all four source
identities and per-reference provenance. The price-project workbook is panel
evidence only; do not present its reimbursement or method codes as official
WS/T 886 or LOINC mappings. Keep the source Markdown and XLSX private.

### `nhc-lab-tests`

Publish the normalized factual WS/T 886 code/name/category/analyte/specimen/scale
projection. Preserve the standard number, dates, conversion filename, SHA256,
size, and table-row source location. Do not distribute the Markdown conversion,
external image, or represent unavailable PDF page numbers as known facts.

## Operational Conditions

- Registry revocation is used when a Release must no longer be recommended.
- Existing user installations are not silently deleted.
- Source or rights corrections receive a new immutable Build Revision.
- Attribution and notice files travel with direct-download artifacts.
- Requests concerning provenance, correction, or takedown are handled by the
  repository maintainers and recorded in versioned metadata.
