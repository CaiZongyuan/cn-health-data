# CN Health Data

CN Health Data is infrastructure for compiling versioned, traceable Chinese
healthcare reference datasets into local query artifacts such as SQLite.

The repository contains working Python dataset compilers and a native Rust
runtime following [`docs/implementation-handbook.md`](docs/implementation-handbook.md).

Current completed and blocked surfaces are tracked in
[`docs/implementation-status.md`](docs/implementation-status.md).

## Bootstrap

Requirements:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run cn-health-build --version
uv run pytest
```

Build and use the native local runtime:

```bash
cargo build -p cn-health

target/debug/cn-health dataset install --local-manifest \
  dist/nhsa-drugs/releases/2026-01-09.r2/manifest.json

target/debug/cn-health drug search 二甲双胍 --json
target/debug/cn-health diagnosis search 糖尿病 --json
```

For a published, rights-approved Registry:

```bash
target/debug/cn-health dataset install nhsa-drugs \
  --registry https://data.example/registry.json \
  --public-key registry.pub
```

Remote installation is unavailable for the current local Candidates because
their Manifests correctly set `releaseEligible` to `false`.

Use `--data-dir <path>` to isolate an installation for testing.

## Source data

Raw source files are not committed. Place explicitly acquired inputs in
`tmp/`, then pass the exact path to the compiler. The current `nhsa-drugs`
baseline is the `总表` sheet in:

```text
tmp/江西省医保药品分类与代码数据库更新表(数据更新至2026年1月9日).xlsx
```

The source must match the SHA256 recorded in
`datasets/nhsa-drugs/dataset.yaml`. The PDF in `tmp/` is not part of this
dataset build.

## Repository areas

- `datasets/`: dataset contracts, schemas, fixtures, and validation rules
- `python/compiler/`: build-time compiler and source adapters
- `schemas/`: machine-readable contract schemas
- `mappings/`: independently versioned terminology mappings
- `docs/`: architecture, source inventory, rights, and implementation guidance
- `rust/cn-health/`: native local installer and query runtime
- `npm/`: deferred native binary distribution wrapper

## Licensing

Repository-owned software code and original project documentation are licensed
under the [MIT License](LICENSE), unless a file says otherwise.

The MIT License does not grant rights to third-party source data or to
normalized SQLite, Parquet, mapping, or other data artifacts by default. The
project does not claim ownership of those source data. Every dataset has its
own rights status and release gate; see [`DATA-NOTICE.md`](DATA-NOTICE.md).
