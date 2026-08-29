# Implementation Status

## Implemented

| Area | Status |
|---|---|
| `nhsa-drugs` compiler | Real XLSX snapshot, fingerprint, streaming normalize/validate, SQLite, FTS, bigram, Parquet, zstd, Diff, Manifest |
| `nhc-icd10-clinical` compiler | Real 2022 XLSX snapshot with main/additional/morphology codes, SQLite, FTS, bigram, Parquet, zstd, Diff, Manifest |
| `loinc-zh-cn` adapter | Synthetic ZIP/CSV and Chinese linguistic-variant join tests, SQLite/FTS/bigram schema |
| `geography-cn` | Real administrative-division, GeoNames place, and postal Candidate with 24,731 rows |
| `names-cn` | Faker `zh_CN` AST-only adapter and 530 weighted name components |
| `population-cn` | UN WPP 2024 Medium projection with 3,171 age/sex rows |
| `laboratory-cn` | Project-authored catalog of 18 Chinese laboratory/vital-sign concepts with exact LOINC 2.83 and preferred UCUM crosswalks |
| Synthetic identity | Deterministic Chinese name/address, `100` phone, `.test` email, project MRN, and `990000` simulated resident ID |
| Synthea support | Fixed-commit profile `2026-08-29.r3`, Bundle localizer, bounded non-root HTTP service, and three-module Docker corpus validation |
| ClinMesh consumer | Candidate Manifest/SQLite import contract, exact Hospital Reference Selection, Profile provenance, Package install, offline restart/reset evidence |
| Native runtime | Rust local install, dual hashes, bounded decompression, integrity check, list/info/versions/use, drug/diagnosis/LOINC get/search, JSON contract |
| Remote distribution | Ed25519 Registry builder and verifier, key pinning, same-origin HTTPS, Manifest/artifact verification |
| npm | Thin native binary resolver and argument/stdio/exit forwarding |

## Local Candidates

- `nhsa-drugs@2026-01-09.r3`
- `nhc-icd10-clinical@2022.r3`
- `geography-cn@2026-08-29.r1`
- `names-cn@40.37.0.r1`
- `population-cn@WPP2024.r1`
- `laboratory-cn@2026-08-30.r1`
- `synthea-cn@2026-08-29.r3` (supported consumer projection)

These are locally built Candidates and are not bundled with the repository.
Their Manifests preserve the source provenance and current distribution metadata;
operators apply the terms associated with their own source copies when using or
sharing record-level artifacts.

## Source-dependent or deferred

- `nhc-procedure-clinical` is deferred by current project direction.
- `laboratory-cn` is the verified project-authored subset used by current
  consumers; it is not represented as the official complete LOINC Chinese
  linguistic variant.
- The separate `loinc-zh-cn` adapter is ready for an official source package
  obtained under the applicable terms. No such package is present in the
  current local inputs, so that Dataset reports no verified Candidate.
- No signing private key or public hosting endpoint is committed. Registry
  keygen/build capabilities are implemented, but production key custody and
  deployment remain an operator responsibility.
