# CN Health Data

CN Health Data is infrastructure for compiling versioned, traceable Chinese
healthcare reference datasets into local query artifacts such as SQLite.

The repository is in bootstrap phase. The current implementation target is the
Python dataset compiler described in
[`docs/implementation-handbook.md`](docs/implementation-handbook.md).

## Bootstrap

Requirements:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
uv run cn-health-build --version
uv run pytest
```

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
- `rust/` and `npm/`: deferred runtime distribution phases

## Licensing

Repository-owned software code and original project documentation are licensed
under the [MIT License](LICENSE), unless a file says otherwise.

The MIT License does not grant rights to third-party source data or to
normalized SQLite, Parquet, mapping, or other data artifacts by default. The
project does not claim ownership of those source data. Every dataset has its
own rights status and release gate; see [`DATA-NOTICE.md`](DATA-NOTICE.md).
