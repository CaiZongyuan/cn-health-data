# Implementation Status

## Implemented

| Area | Status |
|---|---|
| `nhsa-drugs` compiler | Real XLSX snapshot, fingerprint, streaming normalize/validate, SQLite, FTS, bigram, Parquet, zstd, Diff, Manifest |
| `nhc-icd10-clinical` compiler | Real 2022 XLSX snapshot with main/additional/morphology codes, SQLite, FTS, bigram, Parquet, zstd, Diff, Manifest |
| `loinc-zh-cn` compiler | Verified LOINC 2.83 Candidate with 112,405 core concepts, 96,518 official Chinese displays, UCUM, SYSTEM Parts, panels, Schema v2 SQLite/FTS/bigram, Parquet, Diff, Manifest, licenses, and reproducibility evidence |
| `geography-cn` | Real administrative-division, GeoNames place, and postal Candidate with 24,731 rows |
| `names-cn` | Faker `zh_CN` AST-only adapter and 530 weighted name components |
| `population-cn` | UN WPP 2024 Medium projection with 3,171 age/sex rows |
| `nhc-lab-tests` | Complete 399-row WS/T 886—2026 authority projection with appendix-validated code segments, SQLite/FTS/bigram, Parquet, provenance, and reproducibility evidence |
| `laboratory-cn` | Schema v2 adult projection with 84 WS/T 886 tests, 96 references, 15 hospital panels, 88 stable members, units, precision, and explicit healthy simulation metadata |
| Synthetic identity | Deterministic Chinese name/address, `100` phone, `.test` email, project MRN, and `990000` simulated resident ID |
| Synthea support | Fixed-commit r2-backed profile `2026-08-29.r4`, single runtime Manifest, independently checksummed profile archive, self-contained experimental-preview localizer image, bounded non-root HTTP service, and three-module Docker corpus validation |
| Synthea Chinese displays | Pinned 242-module inventory, 2,176 Chinese displays, bounded translation/review workflow, FHIR projector, static zero-gap coverage, and 30-Bundle invariant validation; 18 records are approved and all 51 review flags have evidence resolutions, including 18 recorded upstream module issues |
| ClinMesh consumer | Candidate Manifest/SQLite import contract, exact Hospital Reference Selection, Profile provenance, Package install, offline restart/reset evidence |
| Native runtime | Rust full/default and selective remote install, exact-release atomic materialization, minimum CLI compatibility, complete doctor, schema v1/v2 laboratory get/search, and panel get/search |
| Remote distribution | Eight-Dataset signed public Registry, laboratory v1 history, normalized artifact staging, pinned trust root, Ed25519 verification, same-origin HTTPS, and Manifest/artifact verification |
| npm | Thin native binary resolver, four optional platform packages, and tag-driven package/archive builds |

## Local Candidates

- `nhsa-drugs@2026-01-09.r4`
- `nhc-icd10-clinical@2022.r4`
- `geography-cn@2026-08-29.r2`
- `names-cn@40.37.0.r2`
- `population-cn@WPP2024.r2`
- `nhc-lab-tests@2026.r1`
- `laboratory-cn@2026-09-01.r1` (schema v2; v1 `2026-08-30.r2` retained)
- `loinc-zh-cn@2.83.r2`
- `synthea-cn@2026-08-29.r4` (self-contained runtime consumer projection)
- `synthea-zh-cn@2026-08-30.r1` (experimental display catalog; zero unresolved flags)

These are locally built Candidates whose current normalized zstd/Parquet,
Manifest, report, and license projections are staged in the signed public
distribution. Raw source files, uncompressed SQLite transport copies, historical
revisions, and build caches remain unbundled. Public Manifests preserve source
provenance, attribution, and distribution metadata.

## Source-dependent or deferred

- `nhc-procedure-clinical` is deferred by current project direction.
- `laboratory-cn` intentionally limits references to adults and sex
  `all/male/female`; pediatric, method-specific, regional, pregnancy, and
  disease-driven result models remain out of scope.
- `loinc-zh-cn@2.83.r2` is distributed with the complete and short LOINC license
  artifacts, source-member provenance, and required attribution.
- The public Registry key is pinned in the runtime and its private signing key is
  held as an encrypted CI secret rather than committed. Larger public hosting
  remains a release-operations responsibility.
