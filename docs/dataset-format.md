# Dataset Format

Every dataset has a stable directory under `datasets/` containing:

- `dataset.yaml`: identity, authority, source, versioning, runtime, and rights
- `schema.sql`: canonical SQLite schema
- `workbook.yaml` or `layout.yaml`: source-format fingerprint when required
- `tests/`: synthetic fixtures and dataset-specific assertions

Release manifests and registry entries follow the JSON Schemas under
`schemas/`. The normative details remain in
[`implementation-handbook.md`](implementation-handbook.md).
