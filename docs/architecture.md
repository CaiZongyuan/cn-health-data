# Architecture

The build-time path is:

```text
Declared Source -> Snapshot -> Inspect -> Extract -> Normalize -> Validate
                -> Diff -> SQLite -> Package -> Rights Gate -> Release
```

Python owns acquisition and compilation. SQLite is the canonical runtime
artifact. The Rust CLI verifies and installs local Candidates, maintains an
atomic current pointer, and provides exact/FTS/bigram queries. It can also
verify an Ed25519-signed Registry, pin a public key, enforce same-origin HTTPS,
and install a release-eligible remote artifact. npm remains a thin binary
distribution layer.

See [`implementation-handbook.md`](implementation-handbook.md) for the complete
architecture and invariants.
