# CN Health Data

[English](README.md) | [简体中文](README.zh-CN.md)

CN Health Data is a local-first toolchain for compiling Chinese healthcare
reference data into versioned, traceable, and searchable artifacts. It combines
a Python compiler, immutable Dataset Contracts and Manifests, a native Rust CLI,
and a thin npm launcher.

The project currently builds real drug and diagnosis datasets from explicitly
provided XLSX snapshots. It does not download a presumed latest source, store
patient data, or provide a production clinical system.

> **Data notice:** The MIT License covers repository-owned software and original
> project documentation only. The project does not own or claim ownership of
> third-party healthcare data. Raw inputs and generated record-level artifacts
> have independent rights requirements; see [Data rights](#data-rights-and-license).

## Current Status

| Dataset | Implementation | Verified local Candidate | Records | Public release |
|---|---|---:|---:|---|
| `nhsa-drugs` | Real Jiangxi XLSX `总表` compiler | `2026-01-09.r3` | 269,110 | Blocked pending rights review |
| `nhc-icd10-clinical` | Real NHC 2022 XLSX compiler | `2022.r3` | 37,294 | Blocked pending rights review |
| `loinc-zh-cn` | ZIP/CSV adapter and Rust queries tested with synthetic fixtures | None | None | Blocked on a licensed source package and redistribution evidence |
| `nhc-procedure-clinical` | Contract and schema placeholders only | None | None | Deliberately deferred |

The Candidate identifiers above describe locally verified development builds.
`tmp/`, `.work/`, and `dist/` are ignored by Git, so neither the source files nor
the generated datasets are included in a clone.

Implemented infrastructure includes:

- streaming XLSX extraction, normalization, validation, and source fingerprinting;
- deterministic SQLite output with FTS5 trigram and two-character bigram search;
- Parquet, zstd-compressed SQLite, validation reports, Diffs, and Manifests;
- immutable release revisions and comparison against a previous release;
- local installation with compressed and uncompressed SHA256 verification,
  bounded decompression, and SQLite integrity checks;
- installed-version listing, activation, and rollback;
- exact and literal search commands for drugs, diagnoses, and LOINC;
- Ed25519-signed Registry generation and verified remote installation; and
- an npm wrapper that delegates all behavior to the native binary.

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
                    Rights Gate -> Release/Registry
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
tmp/               Local raw inputs; ignored by Git
.work/             Source snapshots and local working data; ignored by Git
dist/              Immutable local Candidates; ignored by Git
```

## Requirements

Core development requires:

- Git;
- Python 3.12;
- [`uv`](https://docs.astral.sh/uv/);
- Rust 1.96 for the native runtime; and
- Node.js 22 and pnpm 11 only for the npm wrapper.

Real dataset builds additionally require the exact source files declared in the
Dataset Contracts. Unit and integration tests use synthetic fixtures and do not
require the third-party XLSX files.

## Quick Start

Install the locked Python environment and validate the repository contracts:

```bash
uv sync --locked
uv run cn-health-build --version
uv run cn-health-build validate-contracts
uv run pytest
```

Build and test the native CLI:

```bash
cargo build -p cn-health
cargo test --workspace
target/debug/cn-health --version
```

These commands verify the software without building or redistributing real data.

## Source Data

Source acquisition is explicit and local. The compiler never scans `tmp/`, never
chooses a file by modification time, and never synchronizes from an upstream PDF
or website. Pass the exact source path on every build.

The currently declared real inputs are:

| Dataset | Local file | Worksheet | Expected SHA256 |
|---|---|---|---|
| `nhsa-drugs` | `tmp/江西省医保药品分类与代码数据库更新表(数据更新至2026年1月9日).xlsx` | `总表` | `9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67` |
| `nhc-icd10-clinical` | `tmp/疾病分类与代码国家临床版2.0(2022汇总版).xlsx` | `2.0（2022版）` | `e927d8ec0d25a64125e24b26dcc3987b0021b5d8b94c0f4d7ae7e05f1592af52` |

The drug compiler reads only the workbook's `总表`. The downloaded drug PDF in
`tmp/` is not part of this build. The local procedure workbook is also not
consumed because procedure implementation is deferred.

You can verify inputs before building:

```bash
sha256sum \
  'tmp/江西省医保药品分类与代码数据库更新表(数据更新至2026年1月9日).xlsx' \
  'tmp/疾病分类与代码国家临床版2.0(2022汇总版).xlsx'
```

During a build, the compiler verifies the declared SHA256, size, worksheet,
headers, XLSX container fingerprint, and formula expectations. A matching input
is copied to `.work/sources/<sha256>/source.xlsx` as a private content-addressed
snapshot. Source files and snapshots must remain outside commits and releases.

Candidate provenance records the current Git commit and compiler inputs. Normal
CLI builds therefore refuse a dirty Git worktree.

## Build Local Candidates

The examples below assume a fresh `dist/` directory and create revision 1:

```bash
uv run cn-health-build build nhsa-drugs \
  --source 'tmp/江西省医保药品分类与代码数据库更新表(数据更新至2026年1月9日).xlsx' \
  --build-revision 1 \
  --sequence 1

uv run cn-health-build build nhc-icd10-clinical \
  --source 'tmp/疾病分类与代码国家临床版2.0(2022汇总版).xlsx' \
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

## Install and Query Locally

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

The Registry tooling is implemented, but the current real Manifests have
`releaseEligible: false`. They cannot be added to a public Registry until source
rights evidence and the Rights Gate permit the relevant artifact types. There is
also no production signing key or hosting endpoint in this repository.

For a rights-approved Manifest, an operator can generate a raw Ed25519 keypair
and build a signed Registry. The example keeps its development keys and output
under the Git-ignored `.work/` directory; replace the uppercase path placeholders:

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
artifacts at their declared same-origin HTTPS URLs. A client installs the
Registry's recommended, non-revoked release with a separately pinned public key:

```bash
target/debug/cn-health --data-dir .work/runtime dataset install DATASET_ID \
  --registry https://data.example/registry.json \
  --public-key .work/registry/registry.pub
```

The runtime verifies the Registry signature and key ID, Manifest digest and
identity, release eligibility, artifact hashes and sizes, and same-origin URL
policy. Plain HTTP is accepted only for loopback development hosts.

## npm Wrapper

`npm/cn-health` is a thin launcher. It forwards arguments, stdio, signals, and
exit status to the native CLI and does not contain data or query logic.

During local development, point it at a built binary:

```bash
pnpm install --frozen-lockfile
cargo build --release -p cn-health

CN_HEALTH_BINARY="$PWD/target/release/cn-health" \
  node npm/cn-health/bin/cn-health.js \
  --data-dir .work/runtime dataset list --json
```

Published package layouts are expected to provide an optional
`@cn-health/cli-<platform>-<arch>` binary package. Those platform packages are
not currently published by this repository.

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

Dataset parser and build tests use synthetic fixtures. Real source data must not
be copied into tests. When changing a source adapter, update its contract,
fingerprint, validation baseline, provenance, rights record, and tests together.
See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Data Rights and License

Repository-owned software code and original project documentation are licensed
under the [MIT License](LICENSE), unless a specific file says otherwise.

MIT does **not** automatically apply to:

- raw or mirrored third-party source files;
- normalized record-level data derived from third-party sources;
- generated SQLite, Parquet, mapping, or similar data artifacts; or
- third-party names, marks, and other protected material.

Every Dataset Contract and Release Manifest carries its own redistribution state.
The public release path fails closed unless legal basis, evidence, attribution,
review information, and allowed artifact types are recorded. Do not publish the
current real Candidates.

Read [`DATA-NOTICE.md`](DATA-NOTICE.md) and
[`docs/data-rights.md`](docs/data-rights.md) before acquiring, sharing, or
publishing any dataset.

## Scope and Known Limitations

- This project provides reference-data tooling, not medical advice or a
  production clinical decision system.
- It stores reference datasets only and must not contain real patient data.
- Drug compilation intentionally uses the declared Jiangxi XLSX `总表`; no PDF
  synchronization path is implemented.
- Procedure classification is explicitly deferred even if a local workbook is
  present.
- LOINC has adapter and runtime coverage only; a real Candidate awaits a licensed
  package, confirmed member layout and version, and redistribution evidence.
- No current real Candidate is approved for public distribution.
- Production signing-key custody, artifact hosting, and package publishing remain
  operator responsibilities.

## Documentation

- [`docs/implementation-status.md`](docs/implementation-status.md): implemented,
  deferred, and blocked surfaces
- [`docs/implementation-handbook.md`](docs/implementation-handbook.md): normative
  implementation handbook
- [`docs/architecture.md`](docs/architecture.md): concise component architecture
- [`docs/dataset-format.md`](docs/dataset-format.md): Dataset Contract layout
- [`docs/source-inventory.md`](docs/source-inventory.md): source inventory and status
- [`docs/data-rights.md`](docs/data-rights.md): Rights Gate and release policy
- [`DATA-NOTICE.md`](DATA-NOTICE.md): bilingual data ownership and license notice
