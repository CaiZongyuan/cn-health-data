# Contributing

## Development setup

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy python/compiler/src
```

## Dataset changes

- Do not commit raw government or third-party source files.
- Resolve source files explicitly; never scan `tmp/` for a presumed latest file.
- Update the source hash, version, workbook/layout fingerprint, validation
  baseline, provenance, and rights record together.
- Preserve old Release IDs and artifacts. Corrections receive a new Build
  Revision.
- Add synthetic fixtures rather than copied source records.

## Code changes

Keep source-specific parsing in `python/compiler/src/cn_health_compiler/sources/`
and reusable pipeline behavior in `core/`. Run formatting, static checks, and
tests before submitting changes.

By contributing repository-owned software code or original project
documentation, contributors agree that it may be distributed under the MIT
License. Supplying a source file or factual record does not relicense that data;
data contributions must include provenance and evidence that the proposed use
and redistribution are permitted.
