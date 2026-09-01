# CN Health Data

[English](README.md) | [简体中文](README.zh-CN.md)

CN Health Data is a local-first toolchain for compiling reusable Chinese
healthcare reference data into versioned, traceable, and searchable artifacts.
It combines a Python compiler, immutable Dataset Contracts and Manifests, a
native Rust CLI, and a thin npm launcher.

The repository is organized around Chinese health data needed by different
consumers, not around one simulator. It currently builds drug and diagnosis
datasets from explicitly provided XLSX snapshots, a project-authored curated
laboratory catalog, and general-purpose geography, name, and population
Datasets. Synthea is supported through a versioned consumer projection. The
project does not download a presumed latest source, store patient data, or
provide a production clinical system.

> **Data and license:** The MIT License covers repository-owned software and
> original project documentation. Source datasets retain their own terms; this
> project neither owns nor relicenses them. See
> [Data rights](#data-rights-and-license).

## Current Status

| Dataset | Current implementation | Verified build | Records | Public availability |
|---|---|---:|---:|---|
| `nhsa-drugs` | Import, validation, packaging, and search for the drug classification/code workbook `总表` | `2026-01-09.r3` | 269,110 | Local Candidate only; not in the public Registry |
| `nhc-icd10-clinical` | Import, validation, packaging, and search for Clinical Diagnosis Classification 2.0 (2022) | `2022.r3` | 37,294 | Local Candidate only; not in the public Registry |
| `geography-cn` | Versioned administrative divisions, populated places, and postal areas | `2026-08-29.r1` | 24,731 | Local Candidate only; not in the public Registry |
| `names-cn` | Safe static parsing of Chinese surname and given-name components | `40.37.0.r1` | 530 | Local Candidate only; not in the public Registry |
| `population-cn` | Chinese age/sex marginal population distributions | `WPP2024.r1` | 3,171 | Local Candidate only; not in the public Registry |
| `laboratory-cn` | Project-authored Chinese laboratory/vital-sign catalog with exact LOINC and preferred UCUM crosswalks | `2026-08-30.r1` | 18 | Public starter Registry; install with `cn-health init` |
| `loinc-zh-cn` | Complete LOINC 2.83 core plus official Chinese variant, UCUM examples, SYSTEM Parts, and panels | `2.83.r1` | 365,722 | Local Candidate only; artifact-specific rights review pending |
| `nhc-procedure-clinical` | Contract and schema defined; compiler implementation deferred | None | None | Not implemented |

The build identifiers above describe Candidates verified in the current
development workspace. This repository distributes the compiler, runtime,
synthetic test fixtures, and the redistribution-approved `laboratory-cn`
starter Release. `tmp/`, `.work/`, and `dist/` are ignored by Git, so private
source workbooks and other local Candidates are not included in a clone.

Implemented infrastructure includes:

- streaming XLSX extraction, normalization, validation, and source fingerprinting;
- deterministic SQLite output with FTS5 trigram and two-character bigram search;
- Parquet, zstd-compressed SQLite, validation reports, Diffs, and Manifests;
- immutable release revisions and comparison against a previous release;
- local installation with compressed and uncompressed SHA256 verification,
  bounded decompression, and SQLite integrity checks;
- installed-version listing, activation, and rollback;
- exact and literal search commands for drugs, diagnoses, LOINC, and the curated
  laboratory catalog;
- complete LOINC 2.83 compilation with 112,405 core concepts and 96,518
  official Chinese displays;
- a project-authored laboratory/vital-sign catalog with Chinese displays and
  curated LOINC 2.83/UCUM crosswalks;
- deterministic Chinese synthetic names, addresses, `100` phones, and `990000`
  simulated resident IDs;
- a fixed-commit Synthea profile projection, FHIR R4 identity localizer, and
  bounded internal HTTP service;
- a signed public starter Registry, pinned default trust root, `init`, and
  offline `doctor`; and
- tag builds for four native platforms plus an npm wrapper that delegates all
  behavior to the native binary.

For the exact implementation boundary, see
[`docs/implementation-status.md`](docs/implementation-status.md).

## Architecture

```text
Declared source
      |
      v
Snapshot -> Inspect -> Extract -> Normalize -> Validate -> Diff
                                                       |
                                                       v
                         Manifest <- Package <- SQLite + Parquet
                              |
                              v
               Distribution policy -> Release/Registry
                                      |
                                      v
                               Rust local runtime
```

Python owns build-time source handling and artifact compilation. SQLite is the
canonical runtime artifact. The Rust CLI treats every local Candidate and remote
download as untrusted input, verifies it, installs it under a versioned directory,
and atomically changes the active release pointer. npm remains a launcher rather
than a second implementation of runtime behavior.

Each dataset is governed by a contract under `datasets/<dataset-id>/`:

- `dataset.yaml` declares identity, authority, source hash, versioning, validation,
  runtime requirements, and rights status;
- `workbook.yaml` or `layout.yaml` fingerprints source structure when needed; and
- `schema.sql` defines the runtime database and search indexes.

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/implementation-handbook.md`](docs/implementation-handbook.md) for the
full design and invariants.

## Repository Layout

```text
datasets/          Dataset Contracts, source fingerprints, and SQLite schemas
docs/              Architecture, implementation, source, and rights documentation
mappings/          Independently versioned terminology mapping placeholders
npm/               Thin native CLI launcher
python/compiler/   Python compiler package, adapters, and tests
rust/cn-health/    Native installer and query runtime
schemas/           JSON Schemas for contracts, Manifests, Registry, and CLI output
distribution/      Signed public Registry and redistribution-approved starter Release
tmp/               Local raw inputs; ignored by Git
.work/             Source snapshots and local working data; ignored by Git
dist/              Immutable local Candidates; ignored by Git
```

## Requirements

End users can install through npm or use a native release archive:

| Installation | Runtime requirement | Supported platforms |
|---|---|---|
| npm `cn-health@0.2.1` | Node.js 22 or newer | Linux x64, macOS x64/arm64, Windows x64 |
| GitHub native archive | No language runtime | Linux x64, macOS x64/arm64, Windows x64 |

Both options run the same Rust CLI. The npm package only resolves a platform
binary; it does not contain a second query implementation. End users do not
need Python, Rust, `uv`, pnpm, or any source workbook.

Source development requires:

- Git;
- Python 3.12;
- [`uv`](https://docs.astral.sh/uv/);
- Rust 1.96 for the native runtime; and
- Node.js 22 and pnpm 11 only for the npm wrapper.

Real dataset builds additionally require the exact source files declared in the
Dataset Contracts. Unit and integration tests use synthetic fixtures and do not
require the third-party XLSX files.

## Quick Start

### Install With npm

This is the simplest cross-platform installation method:

```bash
npm install --global cn-health@0.2.1
cn-health --version
```

The version command should print:

```text
cn-health 0.2.1
```

npm installs only the optional package matching the current operating system.
For example, Linux x64 installs `@cn-health/cli-linux-x64`; unmet optional
dependencies for the other platforms are expected.

For a temporary check, `npx --yes cn-health@0.2.1 --version` also works. A global
installation is preferable for repeated queries because it avoids resolving the
package every time.

### Install a Native Archive

To run without Node.js, download the matching archive from the
[`v0.2.1` GitHub Release](https://github.com/CaiZongyuan/cn-health-data/releases/tag/v0.2.1):

| System | Release asset |
|---|---|
| Linux x64 | `cn-health-v0.2.1-linux-x64.tar.gz` |
| macOS Intel | `cn-health-v0.2.1-darwin-x64.tar.gz` |
| macOS Apple Silicon | `cn-health-v0.2.1-darwin-arm64.tar.gz` |
| Windows x64 | `cn-health-v0.2.1-win32-x64.tar.gz` |

Extract and run on Linux or macOS:

```bash
tar -xzf cn-health-v0.2.1-linux-x64.tar.gz
./cn-health-v0.2.1-linux-x64/cn-health --version
```

Windows PowerShell can use the system `tar` command:

```powershell
tar -xzf cn-health-v0.2.1-win32-x64.tar.gz
.\cn-health-v0.2.1-win32-x64\cn-health.exe --version
```

Every native archive also contains `LICENSE` and `DATA-NOTICE.md`. macOS
artifacts are not currently Apple-notarized; execution remains subject to the
machine's Gatekeeper and organizational security policy.

### Initialize Starter Data

After installing the CLI, run:

```bash
cn-health init --json
```

The first run downloads, verifies, and installs
`laboratory-cn@2026-08-30.r1` from the built-in HTTPS Registry. Successful output
looks like:

```json
{"command":"init","items":[{"datasetId":"laboratory-cn","releaseId":"laboratory-cn@2026-08-30.r1","status":"installed"}],"profile":"starter","schemaVersion":1}
```

`init` is idempotent; an existing identical Release reports
`already-installed`. Installation verifies:

- the Registry Ed25519 signature and pinned public-key ID;
- the Manifest digest, Dataset/Release identity, and revocation state;
- `releaseEligible` distribution status and same-origin HTTPS URLs;
- SHA256 and size for the transferred zstd file and decompressed SQLite;
- bounded decompression, SQLite `integrity_check`, and application ID; and
- the minimum CLI version declared by the Manifest.

> The public starter currently contains **only 18** project-authored laboratory
> and vital-sign records. Installing the npm package or running `init` does not
> provide the drug, national diagnosis, complete LOINC, geography, name, or
> population Candidates.

### Search and Exact Lookup

Search by literal Chinese text:

```bash
cn-health laboratory search 血糖 --limit 10 --json
```

Retrieve an exact LOINC code:

```bash
cn-health laboratory get 2339-0 --json
```

Code `2339-0` returns the curated Chinese display `血糖`, LOINC system/version,
category, specimen, result type, and preferred UCUM unit `mg/dL`. Search text
must contain at least two Unicode characters. The default result limit is 20;
`--limit` accepts 1 through 200. JSON search output has stable schema, Dataset
and Release identity, query parameters, items, and pagination metadata.

### Inspect the Installation

```bash
cn-health doctor
cn-health dataset list --json
cn-health dataset info laboratory-cn --json
cn-health dataset versions laboratory-cn --json
```

`doctor` checks that the starter is installed, came from a signed Registry, and
can read a required record from the installed SQLite. `doctor --json` also shows
the effective `dataDir` and the default Registry URL compiled into the CLI.

### Data Directory and Offline Operation

Without `--data-dir`, the CLI uses the application data directory assigned by
the operating system for `org.cn-health.cn-health`. Do not guess this path; show
it with:

```bash
cn-health doctor --json
```

For isolated tests, CI, or multiple environments, put the global argument before
the subcommand:

```bash
cn-health --data-dir /absolute/path/to/cn-health-data init
cn-health --data-dir /absolute/path/to/cn-health-data laboratory search 血糖 --json
```

`init` needs network access to the public Registry. After installation, search,
exact lookup, Dataset inspection, and `doctor` do not access the network.
Uninstalling the npm package does not remove the application data directory.

### Upgrade

npm users can upgrade the CLI and repeat the idempotent initialization to adopt
the Registry's current recommended, non-revoked Release:

```bash
npm install --global cn-health@latest
cn-health --version
cn-health init
cn-health doctor
```

Native users download the newer archive and replace their executable. Older
Dataset Releases remain in the data directory; `dataset use` can switch among
installed versions.

### Troubleshooting

- `No cn-health binary for ...`: the platform is unsupported or optional
  dependencies were omitted. Use Node.js 22+ and reinstall with
  `npm install --global cn-health@latest --include=optional`.
- `EACCES`: npm platform packages in `0.2.0` did not preserve Unix executable
  permissions. Upgrade to `0.2.1` or newer.
- `DATASET_NOT_INSTALLED`: run `cn-health init` and confirm the query uses the
  same `--data-dir`.
- `CLI_VERSION_INCOMPATIBLE`: the Manifest requires a newer runtime. Upgrade
  `cn-health`, then initialize again.
- `search query must contain at least two Unicode characters`: provide at least
  two characters, or use `get` when the code is known.
- Registry or HTTPS download errors: initialization requires GitHub Raw access.
  Check proxy, DNS, TLS, and organizational network policy. Do not bypass the
  signature or hash checks.

### Contributor Quick Start

Contributors can clone the repository and prove the same real query with one
command:

```bash
scripts/bootstrap-dev.sh
```

## Source Data

Source acquisition is explicit and local. The compiler never scans `tmp/`, never
chooses a file by modification time, and never synchronizes from an upstream PDF
or website. Pass the exact source path on every build.

The currently declared third-party workbook inputs are:

| Dataset | Input contract | Worksheet | Expected SHA256 |
|---|---|---|---|
| `nhsa-drugs` | Drug classification/code workbook supplied through `DRUG_SOURCE` | `总表` | `9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67` |
| `nhc-icd10-clinical` | Clinical Diagnosis Classification workbook supplied through `DIAGNOSIS_SOURCE` | `2.0（2022版）` | `e927d8ec0d25a64125e24b26dcc3987b0021b5d8b94c0f4d7ae7e05f1592af52` |

The drug compiler reads only the declared workbook's `总表`. The downloaded drug
PDF in `tmp/` is not part of this build. The local procedure workbook is also not
consumed because procedure implementation is deferred.

`laboratory-cn` is different from those imported workbooks: its source is the
repository-owned [`datasets/laboratory-cn/catalog.csv`](datasets/laboratory-cn/catalog.csv).
The catalog's Chinese displays, selection, categories, result types, preferred
UCUM units, and curation notes are project-authored. Its LOINC and UCUM
identifiers continue to identify their respective external standards.

`loinc-zh-cn` uses the authenticated, operator-supplied official
`tmp/Loinc_2.83.zip`. The same archive contains the complete table, Chinese
`zhCN5` linguistic variant, Part files, panels, and LOINC License 5.8. The source
archive is private and ignored by Git; its exact hash, selected member hashes,
layout, counts, attribution, and rights decision are pinned under
[`datasets/loinc-zh-cn/`](datasets/loinc-zh-cn/).

You can verify inputs before building:

```bash
export DRUG_SOURCE=/absolute/path/to/drug-classification.xlsx
export DIAGNOSIS_SOURCE=/absolute/path/to/clinical-diagnosis-2022.xlsx
sha256sum \
  "$DRUG_SOURCE" \
  "$DIAGNOSIS_SOURCE"
```

During a build, the compiler verifies the declared SHA256, size, worksheet,
headers, XLSX container fingerprint, and formula expectations. A matching input
is copied to `.work/sources/<sha256>/source.xlsx` as a private content-addressed
snapshot. Git ignores both the original files and these snapshots, and the
compiler does not package either one as a release artifact.

Candidate provenance records the current Git commit and compiler inputs. Normal
CLI builds therefore refuse a dirty Git worktree.

## Build Local Candidates

The examples below assume a fresh `dist/` directory and create revision 1:

```bash
uv run cn-health-build build nhsa-drugs \
  --source "$DRUG_SOURCE" \
  --build-revision 1 \
  --sequence 1

uv run cn-health-build build nhc-icd10-clinical \
  --source "$DIAGNOSIS_SOURCE" \
  --build-revision 1 \
  --sequence 1

uv run cn-health-build build laboratory-cn \
  --source datasets/laboratory-cn/catalog.csv \
  --build-revision 1 \
  --sequence 1

uv run cn-health-build build loinc-zh-cn \
  --source tmp/Loinc_2.83.zip \
  --build-revision 1 \
  --sequence 1
```

The compiler prints the release directory and Manifest path. Each Candidate has
this shape:

```text
dist/<dataset-id>/releases/<source-version>.r<revision>/
├── data.sqlite
├── data.sqlite.zst
├── data.parquet
├── diff.json
├── manifest.json
└── validation.json
```

Candidate directories are immutable. A build refuses to overwrite an existing
directory. Use a new Build Revision for a compiler or metadata correction while
keeping the same Source Version:

```bash
uv run cn-health-build build nhc-icd10-clinical \
  --source 'tmp/疾病分类与代码国家临床版2.0(2022汇总版).xlsx' \
  --build-revision 2 \
  --sequence 2 \
  --base-release dist/nhc-icd10-clinical/releases/2022.r1
```

This produces `nhc-icd10-clinical@2022.r2`, records `2022.r1` as its
predecessor, and calculates `diff.json` from the base SQLite database. Source
Version, Build Revision, release sequence, compiler version, Dataset Schema
Version, and Manifest Schema Version are intentionally separate dimensions.

## General-Purpose Chinese Data and Synthea Support

`geography-cn`, `names-cn`, and `population-cn` are general-purpose Datasets.
The Synthea profile is a versioned consumer projection rather than a canonical
data model or a release priority for the repository as a whole.

The current implementations reuse pinned upstream reference material while
keeping Dataset contracts, validation, normalization, and release production in
this repository:

| Dataset | Pinned reference material | Implementation choice |
|---|---|---|
| `geography-cn` | AreaCity administrative divisions plus GeoNames China places and postal data | Compile a provenance-preserving composite Candidate; do not depend on either project at runtime |
| `names-cn` | Faker `zh_CN` person provider 40.37.0 | Parse declared literals with Python AST without importing or executing the provider module |
| `population-cn` | UN World Population Prospects 2024 Medium projection | Keep only aggregate China age/sex marginals; do not synthesize unsupported joint distributions |

The verified Synthea combination is:

```text
geography-cn@2026-08-29.r1
names-cn@40.37.0.r1
population-cn@WPP2024.r1
synthea-cn@2026-08-29.r3
Synthea d9d07a6eef91ee5144293b42ab64224d84d124f8
```

Build the profile from three Candidate Releases:

```bash
uv run cn-health-build synthea profile \
  --geography-release dist/geography-cn/releases/2026-08-29.r1 \
  --names-release dist/names-cn/releases/40.37.0.r1 \
  --population-release dist/population-cn/releases/WPP2024.r1 \
  --output-root dist/synthea-cn-profile/releases \
  --profile-version 2026-08-29 \
  --build-revision 3 \
  --reference-year 2026 \
  --synthea-commit d9d07a6eef91ee5144293b42ab64224d84d124f8
```

Localize one self-contained Synthea FHIR R4 collection Bundle:

```bash
uv run cn-health-build synthea localize \
  --input /path/to/raw-bundle.json \
  --output .work/localized-bundle.json \
  --profile dist/synthea-cn-profile/releases/2026-08-29.r3 \
  --geography-release dist/geography-cn/releases/2026-08-29.r1 \
  --names-release dist/names-cn/releases/40.37.0.r1 \
  --population-release dist/population-cn/releases/WPP2024.r1 \
  --seed patient-1
```

Long-running consumers can build `Dockerfile.synthea-localizer` or run
`cn-health-synthea-service`. The service verifies the profile content, files,
three Candidate dependencies, and translation catalog at startup. It requires
an explicit catalog path and clinical display projection ID; neither is guessed:

```bash
CN_HEALTH_SYNTHEA_TRANSLATION_CATALOG_PATH=translations/synthea-zh-cn/catalog.jsonl \
CN_HEALTH_SYNTHEA_CLINICAL_DISPLAY_PROJECTION_ID=synthea-zh-cn@2026-08-30.r1 \
CN_HEALTH_SYNTHEA_EXPECTED_CATALOG_SHA256=d7a25fc414d4008cf59145fd8fc3448556635dd2d5ab8e1e7974bc236f825811 \
uv run cn-health-synthea-service \
  --profile dist/synthea-cn-profile/releases/2026-08-29.r3 \
  --geography-release dist/geography-cn/releases/2026-08-29.r1 \
  --names-release dist/names-cn/releases/40.37.0.r1 \
  --population-release dist/population-cn/releases/WPP2024.r1
```

The service loads the catalog only when its canonical SHA-256 exactly matches
the required expected hash, binding the projection ID to the deployed content
instead of trusting a mutable path. It then applies identity localization first
and projects displays from the verified catalog. It accepts `approved`, `human-reviewed`, and
`machine-checked`, preserves a source display when its translation is missing,
and returns a bounded `TRANSLATION_GAP` warning without rejecting the Bundle. It
still fails closed for invalid requests, Bundle localization failures, catalog
hash drift, and provenance errors. `Claim` and `ExplanationOfBenefit` are removed
with their reference dependents. Health and successful responses report the
projection ID, catalog hash, language, record count, and `experimental-preview`
review mode. No external translation API is called. The Python library localizer
remains identity-only unless explicitly composed. See
[`docs/synthea-cn-spec.md`](docs/synthea-cn-spec.md) for the full contract and
Docker acceptance criteria.

After identity localization, apply the pinned Chinese clinical display catalog:

```bash
uv run cn-health-build synthea translation project \
  --input .work/localized-bundle.json \
  --catalog translations/synthea-zh-cn/catalog.jsonl \
  --output .work/localized-bundle.zh-CN.json \
  --report .work/localized-bundle.zh-CN.report.json \
  --release-id synthea-zh-cn@2026-08-30.r1 \
  --allow-machine-draft
```

The catalog covers all 2,149 terms discovered in the pinned 242 modules, 27
exporter displays, and four runtime projection gaps found by the all-module smoke. Twenty-two records are `approved`; 2,158 records
are independently `machine-checked`. Evidence review resolved all 51 original
flags and records 18 Synthea module context or code-selection issues. Strict CLI
mode uses only approved records. The CLI experimental switch is named for the
least-reviewed stage it permits; this catalog currently has no machine-draft records.
The runtime service accepts human-reviewed and machine-checked records, but never machine-draft records,
under an explicit experimental distribution boundary. Translation APIs are
never called by CI, Bundle projection, or runtime services. See
[`translations/synthea-zh-cn/coverage.json`](translations/synthea-zh-cn/coverage.json).

## Curated Laboratory Concepts

`laboratory-cn@2026-08-30.r1` contains 18 laboratory and vital-sign concepts
needed by the currently validated consumers. It pairs project-authored Chinese
displays and catalog metadata with exact LOINC 2.83 codes and preferred UCUM
units. The same Candidate Contract, deterministic SQLite/Parquet packaging,
Manifest verification, FTS, and bigram indexing used by the other compilers
apply to this catalog.

This focused catalog is not the official complete LOINC Chinese linguistic
variant. The separate `loinc-zh-cn@2.83.r1` Candidate contains all 112,405 core
concepts and 96,518 official Chinese translations. Consumers that only need the
reviewed project subset can still use `laboratory-cn` without loading the full
terminology. See
[`datasets/laboratory-cn/README.md`](datasets/laboratory-cn/README.md).

## Install and Query Local Candidates

Build the runtime, then install the Candidate using its local Manifest. An
explicit data directory keeps the example isolated and reproducible:

```bash
cargo build -p cn-health

target/debug/cn-health --data-dir .work/runtime dataset install \
  --local-manifest dist/nhsa-drugs/releases/2026-01-09.r1/manifest.json

target/debug/cn-health --data-dir .work/runtime dataset install \
  --local-manifest dist/nhc-icd10-clinical/releases/2022.r1/manifest.json
```

Local installation verifies the compressed artifact hash and size, decompresses
within the Manifest's declared bound, verifies the uncompressed hash and size,
runs SQLite `integrity_check`, and checks the database application ID. A local
Candidate is reported as `local-untrusted`; that label distinguishes local
installation from a release authenticated by a signed Registry.

Search by literal Chinese text or retrieve an exact code:

```bash
target/debug/cn-health --data-dir .work/runtime drug search 二甲双胍 --limit 10 --json
target/debug/cn-health --data-dir .work/runtime drug get XA10BAE021A010010201650 --json

target/debug/cn-health --data-dir .work/runtime diagnosis search 糖尿病 --limit 10 --json
target/debug/cn-health --data-dir .work/runtime diagnosis get E14.900x001 --json
```

Search queries must contain at least two Unicode characters. The default result
limit is 20 and the accepted range is 1 through 200. `--json` search output has a
stable envelope containing `schemaVersion`, command and dataset identity, query
metadata, ranked `items`, and pagination metadata. Exact `get` output is always a
single JSON object.

Manage installed datasets and switch the active version:

```bash
target/debug/cn-health --data-dir .work/runtime dataset list --json
target/debug/cn-health --data-dir .work/runtime dataset info nhsa-drugs --json
target/debug/cn-health --data-dir .work/runtime dataset versions nhsa-drugs --json
target/debug/cn-health --data-dir .work/runtime dataset use \
  nhsa-drugs nhsa-drugs@2026-01-09.r1
```

Installing another revision stores it alongside existing versions and makes it
active. `dataset use` changes only the atomic current pointer, so rollback does
not modify either installed release.

Without `--data-dir`, the CLI uses the operating system's application data
directory for the `org.cn-health.cn-health` project identity.

## Signed Registry and Remote Installation

The repository provides a public starter Registry verified by a public key
pinned in the CLI. It currently contains only the explicitly eligible
`laboratory-cn@2026-08-30.r1` Release. Building another Candidate locally never
makes it publicly distributable.

When an operator has prepared distribution metadata consistent with the terms
applicable to the source and intended use, they can generate a raw Ed25519
keypair and build a signed Registry. The example keeps its development keys and
output under the Git-ignored `.work/` directory; replace the uppercase path
placeholders:

```bash
uv run cn-health-build registry keygen \
  --private-key .work/registry/registry.key \
  --public-key .work/registry/registry.pub

uv run cn-health-build registry build \
  dist/DATASET_ID/releases/RELEASE/manifest.json \
  --manifest-base-url https://data.example/releases \
  --private-key .work/registry/registry.key \
  --output .work/registry/registry.json \
  --signature .work/registry/registry.json.sig
```

Production private keys must remain outside the repository checkout and public
host. Publish the Registry, detached signature, Manifests, and compressed
artifacts at their declared same-origin HTTPS URLs. `cn-health init` uses the
built-in channel. An operator can also install a recommended, non-revoked
Release from another Registry with a separately pinned public key:

```bash
target/debug/cn-health --data-dir .work/runtime dataset install DATASET_ID \
  --registry https://data.example/registry.json \
  --public-key .work/registry/registry.pub
```

The runtime verifies the Registry signature and key ID, Manifest digest and
identity, release eligibility, artifact hashes and sizes, and same-origin URL
policy. Plain HTTP is accepted only for loopback development hosts.

## npm Wrapper

The public [`cn-health`](https://www.npmjs.com/package/cn-health) package is a
thin JavaScript launcher. It forwards arguments, stdio, signals, and exit status
to the native CLI and contains no data or query logic. Platform packages are:

- `@cn-health/cli-linux-x64`;
- `@cn-health/cli-darwin-x64`;
- `@cn-health/cli-darwin-arm64`; and
- `@cn-health/cli-win32-x64`.

The launcher resolves the binary in this order:

1. an explicit `CN_HEALTH_BINARY` development override;
2. the optional platform package matching `process.platform/process.arch`; and
3. the source checkout's `target/release/cn-health` development build.

If the resolved file does not exist, the launcher fails explicitly. It never
downloads an unverified executable or falls back to a JavaScript query
implementation. Unix platform packages in `0.2.0` lacked executable permissions
and are superseded by `0.2.1`.

During local development, point it at a built binary:

```bash
pnpm install --frozen-lockfile
cargo build --release -p cn-health

CN_HEALTH_BINARY="$PWD/target/release/cn-health" \
  node npm/cn-health/bin/cn-health.js \
  --data-dir .work/runtime dataset list --json
```

The tag release workflow builds native archives and npm platform packages for
Linux x64, macOS x64/arm64, and Windows x64. It publishes platform packages
before the launcher that depends on them. Publication skips versions already
present in npm, so an interrupted run can safely resume from the GitHub Release
`.tgz` assets.

## Development and Testing

Run the full local checks. The Python and Rust commands match the repository CI;
the final command covers the npm wrapper separately:

```bash
uv sync --locked
uv run ruff check .
uv run mypy python/compiler/src
uv run pytest

cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace

pnpm --filter cn-health test
```

Dataset parser and build tests use only synthetic fixtures; they do not
incorporate records from the source workbooks. When changing a source adapter,
update its contract, fingerprint, validation baseline, provenance, distribution
metadata, and tests together. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Data Rights and License

Repository-owned software code and original project documentation are licensed
under the [MIT License](LICENSE), unless a specific file says otherwise.

MIT does **not** automatically apply to:

- raw or mirrored third-party source files;
- normalized record-level data derived from third-party sources;
- generated SQLite, Parquet, mapping, or similar data artifacts; or
- third-party names, marks, and other protected material.

Third-party data remains governed by its source terms. The repository's MIT
License neither changes those terms nor grants additional permission. Dataset
Contracts and Release Manifests provide fields for recording provenance,
attribution, and distribution metadata. Anyone distributing a data artifact is
responsible for confirming and following the terms that apply to that source.

Read [`DATA-NOTICE.md`](DATA-NOTICE.md) and
[`docs/data-rights.md`](docs/data-rights.md) before acquiring, sharing, or
publishing any dataset.

## Scope and Known Limitations

- This project provides reference-data tooling, not medical advice or a
  production clinical decision system.
- It processes reference datasets and does not store real patient data.
- Drug compilation uses the declared workbook's `总表`; no PDF synchronization
  path is implemented.
- Procedure classification is explicitly deferred even if a local workbook is
  present.
- `laboratory-cn` is a curated project catalog, not the complete official LOINC
  Chinese linguistic variant.
- `loinc-zh-cn@2.83.r1` is verified locally but remains
  `releaseEligible: false`; its third-party copyright notices require an
  artifact-specific review before public Registry distribution.
- `synthea-zh-cn` covers the pinned Synthea version and all 51 ambiguities have
  evidence resolutions, but 2,158 displays remain machine-checked rather than
  clinician-approved; it is not an official terminology language package.

## Documentation

- [`docs/implementation-status.md`](docs/implementation-status.md): implementation
  boundaries and current gaps
- [`docs/implementation-handbook.md`](docs/implementation-handbook.md): normative
  implementation handbook
- [`docs/synthea-cn-spec.md`](docs/synthea-cn-spec.md): executable specification
  for Chinese datasets, Synthea projection, and consumer integration
- [`docs/loinc-zh-cn-spec.md`](docs/loinc-zh-cn-spec.md): source, model, build, and
  acceptance specification for the complete official Simplified Chinese LOINC Candidate
- [`docs/synthea-zh-localization-plan.md`](docs/synthea-zh-localization-plan.md):
  implementation plan for Chinese clinical displays and bounded API translation
- [`docs/architecture.md`](docs/architecture.md): concise component architecture
- [`docs/dataset-format.md`](docs/dataset-format.md): Dataset Contract layout
- [`docs/source-inventory.md`](docs/source-inventory.md): source inventory and status
- [`docs/data-rights.md`](docs/data-rights.md): sources, license scope, and distribution metadata
- [`DATA-NOTICE.md`](DATA-NOTICE.md): bilingual data ownership and license notice
