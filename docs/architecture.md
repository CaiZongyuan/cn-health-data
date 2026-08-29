# Architecture

The build-time path is:

```text
Declared Source -> Snapshot -> Inspect -> Extract -> Normalize -> Validate
                -> Diff -> SQLite -> Package -> Rights Gate -> Release
```

Python owns acquisition and compilation. SQLite is the canonical runtime
artifact. The Rust CLI and npm distribution wrapper are deferred until the
Dataset Contract and JSON interface are stable.

See [`implementation-handbook.md`](implementation-handbook.md) for the complete
architecture and invariants.
