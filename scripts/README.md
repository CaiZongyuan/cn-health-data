# Scripts

Repository-wide maintenance and release orchestration scripts belong here.

- `bootstrap-dev.sh` installs locked development dependencies, builds the native
  runtime, initializes all signed public Datasets, and proves a real query.
- `sign-public-registry.sh` rebuilds the public Registry with an externally
  stored Ed25519 private key. It rejects every ineligible Manifest through the
  compiler Registry gate.
- `publish-npm-packages.sh` publishes platform packages before the launcher,
  skips versions already present in npm, and rejects unexpected package names.
Dataset parsing logic belongs in the Python compiler package, not in ad-hoc
shell scripts.
