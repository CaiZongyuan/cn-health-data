# Minimize current.json to an active storage key

- Status: proposed
- Class: simplification
- Date: 2026-08-29

## Context

The Rust runtime stores immutable release facts in each installed
`manifest.json` and trust metadata in `install.json`. It also copies those facts
into the mutable dataset-level `current.json` pointer.

## Evidence

`CurrentPointer` currently stores `releaseId`, `sequence`, `storageKey`,
`sourceVersion`, `buildRevision`, `relativePath`, and `trust`.

- `current_database()` ignores `relativePath` and safely derives the database
  path from Dataset ID plus `storageKey`.
- `releaseId`, `sequence`, `sourceVersion`, and `buildRevision` already exist in
  the selected release's Manifest.
- `trust` already exists in that release's `install.json`.
- `dataset list`, query metadata, and version activation consume the copied
  values, so a partial write or manual edit can make current state disagree with
  immutable installed metadata.

Exact-symbol searches found no independent fact owned exclusively by
`current.json`; it is a projection plus one selection key.

## Proposal

In a versioned current-pointer schema, retain only:

```json
{
  "schemaVersion": 2,
  "storageKey": "2026-01-09.r2"
}
```

After reading the pointer, load and validate `manifest.json` and `install.json`
from the selected release. Construct list/info/query metadata from those
authoritative files.

Support schema v1 reads during one compatibility window, always write schema
v2, then remove v1 after no supported runtime emits it.

## Consequences

- Removes six duplicated mutable fields and the unused `relativePath` contract.
- Adds two small JSON reads when opening a Dataset; SQLite query cost dominates
  this overhead, and callers can cache one resolved active-release object per
  command.
- Requires a deliberate current-pointer wire-version migration and golden tests,
  so it should not be folded into unrelated installer work.

## Rejected alternative

Making `current.json` authoritative would require removing or weakening the
same facts in immutable Manifests and install metadata, harming provenance and
per-release trust. The pointer should remain selection state, not release data.
