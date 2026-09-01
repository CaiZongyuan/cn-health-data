# cn-health

Native, local-first CLI access to versioned Chinese healthcare reference data.
The npm package is a thin launcher around the Rust runtime; it does not contain
data or reimplement queries in JavaScript.

## Install

Node.js 22 or newer is required for the launcher:

```bash
npm install --global cn-health@0.2.1
cn-health --version
```

Supported packages are selected automatically:

| Platform | Optional package |
|---|---|
| Linux x64 | `@cn-health/cli-linux-x64` |
| macOS Intel | `@cn-health/cli-darwin-x64` |
| macOS Apple Silicon | `@cn-health/cli-darwin-arm64` |
| Windows x64 | `@cn-health/cli-win32-x64` |

Do not install with `--omit=optional`; the launcher needs the matching native
package. Version `0.2.0` had incorrect Unix executable permissions and is
superseded by `0.2.1`.

## First Query

```bash
cn-health init
cn-health laboratory search 血糖 --json
cn-health laboratory get 2339-0 --json
cn-health doctor
```

`init` verifies and installs the signed public starter Release. The starter
currently contains 18 project-authored laboratory and vital-sign records; it
does not include the repository's local-only drug, diagnosis, complete LOINC,
geography, name, or population Candidates.

After initialization, queries and `doctor` work offline. Use
`cn-health doctor --json` to inspect the effective data directory and Registry.

## Development Override

Set `CN_HEALTH_BINARY` to exercise the launcher against a local build:

```bash
cargo build --release -p cn-health
CN_HEALTH_BINARY="$PWD/target/release/cn-health" \
  node npm/cn-health/bin/cn-health.js --version
```

Full data rights, source provenance, and contributor documentation live in the
[repository](https://github.com/CaiZongyuan/cn-health-data).
