# Architecture

The build-time path is:

```text
Declared Source -> Snapshot -> Inspect -> Extract -> Normalize -> Validate
                -> Diff -> SQLite -> Package -> Distribution Gate -> Release
```

Python owns acquisition and compilation. SQLite is the canonical runtime
artifact. The Rust CLI verifies and installs local Candidates, maintains an
atomic current pointer, and provides exact/FTS/bigram queries. It can also
verify an Ed25519-signed Registry, pin a public key, enforce same-origin HTTPS,
and install a release-eligible remote artifact. npm remains a thin binary
distribution layer.
Exact-release materialization reuses that trust boundary and atomically emits
the original Manifest, verified uncompressed SQLite, and a consumer receipt;
consumers never inspect the runtime's private data-directory layout.

See [`implementation-handbook.md`](implementation-handbook.md) for the complete
architecture and invariants.

The implementation contract for general-purpose Chinese geography, population,
name, drug, diagnosis, and laboratory datasets, their supported Synthea
projection, and downstream consumer integration is defined in
[`synthea-cn-spec.md`](synthea-cn-spec.md).
