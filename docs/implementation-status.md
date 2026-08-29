# Implementation Status

## Implemented

| Area | Status |
|---|---|
| `nhsa-drugs` compiler | Real XLSX snapshot, fingerprint, streaming normalize/validate, SQLite, FTS, bigram, Parquet, zstd, Diff, Manifest |
| `nhc-icd10-clinical` compiler | Real 2022 XLSX snapshot with main/additional/morphology codes, SQLite, FTS, bigram, Parquet, zstd, Diff, Manifest |
| `loinc-zh-cn` adapter | Synthetic ZIP/CSV and Chinese linguistic-variant join tests, SQLite/FTS/bigram schema |
| Native runtime | Rust local install, dual hashes, bounded decompression, integrity check, list/info/versions/use, drug/diagnosis/LOINC get/search, JSON contract |
| Remote distribution | Ed25519 Registry builder and verifier, key pinning, same-origin HTTPS, Manifest/artifact verification |
| npm | Thin native binary resolver and argument/stdio/exit forwarding |

## Local Candidates

- `nhsa-drugs@2026-01-09.r3`
- `nhc-icd10-clinical@2022.r3`

Both are local and `releaseEligible: false`. Their SQLite, Parquet, and other
record-level artifacts must not be published until source rights evidence is
recorded and the Rights Gate passes.

## Deliberately deferred or blocked

- `nhc-procedure-clinical` is deferred by current project direction.
- A real `loinc-zh-cn` Candidate is blocked because no licensed source package,
  exact member layout, source version, or redistribution evidence is present.
- No signing private key or public hosting endpoint is committed. Registry
  keygen/build capabilities are implemented, but production key custody and
  deployment remain an operator responsibility.
