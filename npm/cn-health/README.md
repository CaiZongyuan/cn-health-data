# cn-health

Native, local-first CLI access to versioned Chinese healthcare reference data.
The npm package is a thin launcher around the Rust runtime; it does not contain
data or reimplement queries in JavaScript.

## Install

Node.js 22 or newer is required for the launcher:

```bash
npm install --global cn-health@0.5.0
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
superseded by current releases.

## First Query

```bash
cn-health init
cn-health laboratory search 白细胞 --json
cn-health laboratory get 0100101A --json
cn-health laboratory panel get CN-LAB-CBC-5DIFF --json
cn-health doctor
```

`init` verifies and installs all eight current public Datasets: drug, diagnosis,
complete Chinese LOINC, WS/T 886 terminology, geography, names, population, and
the adult laboratory runtime. Use `--only DATASET_ID[,DATASET_ID...]` for
selective installation.
Raw source workbooks and archives are not distributed.

Consumers that need an exact immutable Release can materialize its original
Manifest and verified uncompressed SQLite without depending on the runtime data
directory layout:

```bash
cn-health dataset materialize laboratory-cn laboratory-cn@2026-09-01.r1 \
  --registry https://example.test/registry.json \
  --public-key ./registry.pub \
  --output ./staging/laboratory-cn \
  --json
```

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
