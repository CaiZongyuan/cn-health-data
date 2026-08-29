# Remove inactive v1 surfaces until they have consumers

- Status: proposed
- Class: simplification
- Date: 2026-08-29

## Context

The first `nhsa-drugs` Candidate now completes Source Snapshot, workbook
inspection, streaming normalization and validation, deterministic SQLite,
FTS5 trigram search, zstd packaging, and Manifest generation. The build also
reveals several bootstrap surfaces that imply behavior they do not provide.

## Evidence

- `drug_search_bigram` is created only by
  `datasets/nhsa-drugs/schema.sql`. No production code inserts into or queries
  it. The real `2026-01-09.r1` Candidate contains 0 bigram rows while its FTS
  table contains 269,110 rows.
- `max_relative_decrease` and `max_relative_increase` occur in the Dataset
  Contract, tests, and `RecordCountRules`, but `DrugRecordValidator.finish()`
  never reads them. Only the absolute baseline and minimum are enforced.
- `PipelineStage` and `DiffSummary` have no imports or runtime consumers. Their
  module definitions are the only exact-symbol matches.
- `SQLiteArtifact.record_count` duplicates
  `SQLiteArtifact.validation.record_count`; both are asserted in tests and
  originate from the same validator result.
- `CandidateBuild.manifest` has no consumer. The CLI uses only `release_dir`
  and `manifest_path`, and tests read the persisted Manifest.

Generated output, tests, documentation, and fixtures were classified separately
from production consumers for these searches.

## Proposal

Before the first public or shared v1 artifact, remove inactive surfaces rather
than shipping placeholders:

1. Remove `drug_search_bigram` until a two-character query path both populates
   and consumes it. State explicitly that v0.1 substring search requires at
   least three Unicode characters.
2. Remove the relative count thresholds until Diff accepts a previous Release
   and enforces them, or implement that comparison before retaining the fields.
3. Remove the unused `PipelineStage` and `DiffSummary` definitions. Reintroduce
   them only when a second production consumer needs those types.
4. Collapse the duplicate `SQLiteArtifact.record_count` and unused
   `CandidateBuild.manifest` fields during the same pre-release API cleanup.

Any SQLite schema change after a Candidate is shared must use a new Dataset
Schema Version and Build Revision. The current Candidate is local,
experimental, and `releaseEligible: false`, so the lowest-cost window is before
its first external consumer.

## Alternatives considered

- Implement bigram indexing and previous-Release comparison now. This preserves
  the declared surfaces but expands behavior and testing beyond the current
  v0.1 query/build scope.
- Keep the placeholders as roadmap markers. This saves short-term edits but
  makes schemas and validation config overstate actual guarantees.

## Explicit non-candidates

- Do not combine workbook inspection and extraction. The first pass prevents
  parsing after a changed layout, formula, or container fingerprint.
- Do not remove the content-addressed Source Snapshot. Its second hash detects
  source mutation during copy and supplies reproducible provenance.
- Do not remove SQLite staging or sorted final insertion. They isolate invalid
  records and produce byte-identical artifacts independent of source row order.
