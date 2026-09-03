# Public Data Distribution

This directory contains the current normalized public Releases. It intentionally
does not mirror the local multi-revision `dist/` tree or any raw source file.

The signed [`registry.json`](registry.json) is the machine-readable index used
by `cn-health init`. Each public Manifest declares only files that exist in this
directory.

| Dataset | Release | Records | SQLite zstd | Installed SQLite |
|---|---|---:|---:|---:|
| `geography-cn` | [`2026-08-29.r2`](releases/geography-cn/2026-08-29.r2/manifest.json) | 24,731 | [2.02 MiB](releases/geography-cn/2026-08-29.r2/data.sqlite.zst) | 9.50 MiB |
| `laboratory-cn` | [`2026-09-01.r1`](releases/laboratory-cn/2026-09-01.r1/manifest.json) | 84 tests, 96 references, 15 panels | [19.39 KiB](releases/laboratory-cn/2026-09-01.r1/data.sqlite.zst) | 160 KiB |
| `nhc-lab-tests` | [`2026.r1`](releases/nhc-lab-tests/2026.r1/manifest.json) | 399 | [51.31 KiB](releases/nhc-lab-tests/2026.r1/data.sqlite.zst) | 288 KiB |
| `loinc-zh-cn` | [`2.83.r2`](releases/loinc-zh-cn/2.83.r2/manifest.json) | 365,722 | [51.46 MiB](releases/loinc-zh-cn/2.83.r2/data.sqlite.zst) | 534.88 MiB |
| `names-cn` | [`40.37.0.r2`](releases/names-cn/40.37.0.r2/manifest.json) | 530 | [18.88 KiB](releases/names-cn/40.37.0.r2/data.sqlite.zst) | 148 KiB |
| `nhc-icd10-clinical` | [`2022.r4`](releases/nhc-icd10-clinical/2022.r4/manifest.json) | 37,294 | [2.65 MiB](releases/nhc-icd10-clinical/2022.r4/data.sqlite.zst) | 13.62 MiB |
| `nhsa-drugs` | [`2026-01-09.r4`](releases/nhsa-drugs/2026-01-09.r4/manifest.json) | 269,110 | [19.09 MiB](releases/nhsa-drugs/2026-01-09.r4/data.sqlite.zst) | 225.19 MiB |
| `population-cn` | [`WPP2024.r2`](releases/population-cn/WPP2024.r2/manifest.json) | 3,171 | [105.37 KiB](releases/population-cn/WPP2024.r2/data.sqlite.zst) | 748 KiB |

The recommended SQLite download is 75.40 MiB and expands to approximately
784.50 MiB. The immutable schema v1
[`laboratory-cn@2026-08-30.r2`](releases/laboratory-cn/2026-08-30.r2/manifest.json)
remains available and is listed as a historical Release in the Registry.
Every Release directory also contains its declared Parquet exports, validation
report, Diff, attribution, and license artifacts where applicable.

## Recommended Installation

The CLI verifies the Registry signature, Manifest digest, compressed and
uncompressed hashes, bounded decompression, and SQLite integrity:

```bash
npm install --global cn-health@0.4.0
cn-health init
cn-health doctor
```

Install selected Datasets with:

```bash
cn-health init --only nhsa-drugs,nhc-icd10-clinical
```

## Direct Files

Consumers that do not use the CLI can download the zstd or Parquet links from a
Release Manifest. Decompress SQLite with a standard zstd implementation:

```bash
zstd -d data.sqlite.zst -o data.sqlite
```

Verify both the transport SHA256 and the Manifest's `uncompressedSha256` before
using the database. The Registry signature and public key are
[`registry.json.sig`](registry.json.sig) and [`registry.pub`](registry.pub).

## Synthea Profile

The separately versioned
[`synthea-cn@2026-08-29.r4`](profiles/synthea-cn/2026-08-29.r4/manifest.json)
resource tree targets Synthea commit
`d9d07a6eef91ee5144293b42ab64224d84d124f8` and the current r2 identity
Datasets. The self-contained localizer image and its release contract are
documented in [`../docs/synthea-runtime.md`](../docs/synthea-runtime.md).

## Source Boundary

Public artifacts are normalized projections. Raw XLSX, ZIP, PDF, CSV source
packages, authenticated downloads, source snapshots, caches, historical
duplicate revisions, and logs are excluded. Source identity, versions, hashes,
attribution, and notices remain in each Manifest. See
[`../DATA-NOTICE.md`](../DATA-NOTICE.md) and
[`../docs/publication-decision.md`](../docs/publication-decision.md).
