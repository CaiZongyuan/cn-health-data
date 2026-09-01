# Starter Distribution Specification

Status: Accepted for implementation  
Target: `cn-health` 0.2.0  
Tracking: GitHub issue #2

## 1. Problem

The repository currently proves that compilers and runtimes can be built, but
it does not give an end user any data to query. Source workbooks and local
Candidates are intentionally excluded from Git, no platform binary is
published, the CLI has no default Registry, and the only public Dataset is not
exposed by the runtime query interface.

A release is not usable until an end user can install a binary, initialize an
eligible Dataset, and return a real record without a compiler toolchain or a
private source file.

## 2. Product Boundary

This specification delivers one complete public distribution slice:

1. prebuilt native CLI packages;
2. a pinned Registry trust root and default Registry location;
3. a `starter` profile containing `laboratory-cn`;
4. idempotent initialization;
5. laboratory exact lookup and Chinese text search;
6. diagnostics and machine-readable output; and
7. clean-checkout and release automation.

The compiler remains a contributor and operator tool. It is not an end-user
runtime dependency.

## 3. Data Boundary

The public Registry MUST include only Manifests whose rights metadata contains
`releaseEligible: true` and artifact-specific evidence. The initial Registry
contains only:

```text
laboratory-cn@2026-08-30.r1
```

The catalog is project-authored and contains 18 curated laboratory and vital
sign concepts. It is deliberately small, but it is real product data rather
than a synthetic test fixture.

Drug, diagnosis, complete LOINC, geography, names, and population Candidates
MUST NOT enter the starter Registry while their current Contracts say
`releaseEligible: false`. A later rights review may publish each independently;
one unresolved source must not block an otherwise eligible Dataset.

Raw third-party sources and the existing local `dist/` tree remain untracked.

## 4. Distribution Topology

The repository owns a small, explicitly public distribution tree:

```text
distribution/
|-- registry.json
|-- registry.json.sig
|-- registry.pub
`-- releases/
    `-- laboratory-cn/
        `-- 2026-08-30.r1/
            |-- manifest.json
            |-- data.sqlite
            |-- data.sqlite.zst
            |-- data.parquet
            |-- diff.json
            `-- validation.json
```

The default channel is served over HTTPS from the repository's public raw-file
origin. The Registry, signature, Manifest, and artifact URLs share an origin as
required by the runtime verifier. The CLI embeds only the public verification
key and default Registry URL; it never embeds or downloads a private key.

The Registry private key MUST live outside the checkout. CI receives it only
through an encrypted repository secret. Key rotation requires a new CLI trust
root or an explicitly specified `--public-key` override.

The checked-in distribution tree is an intentional exception for this small,
redistribution-approved starter Dataset. Large or third-party Releases belong
on immutable release or object storage, referenced by the same signed Registry
contract.

## 5. CLI Contract

### 5.1 Initialization

```text
cn-health init [--profile starter] [--registry URL --public-key PATH] [--json]
```

Rules:

- `starter` is the only profile in 0.2.0 and installs `laboratory-cn`.
- With no distribution overrides, the command uses the compiled-in Registry
  URL and public key.
- `--registry` and `--public-key` are an all-or-nothing pair.
- Repeating initialization is successful and reports an already-installed
  Dataset rather than failing.
- Installation still verifies the Registry signature, key ID, Manifest digest,
  release eligibility, same-origin URLs, compressed and uncompressed hashes,
  bounded decompression, SQLite integrity, and application ID.
- Initialization MUST NOT silently fall back to unsigned or bundled local data.

Successful JSON output uses this shape:

```json
{
  "schemaVersion": 1,
  "command": "init",
  "profile": "starter",
  "items": [
    {
      "datasetId": "laboratory-cn",
      "releaseId": "laboratory-cn@2026-08-30.r1",
      "status": "installed"
    }
  ]
}
```

`status` is `installed` or `already-installed`.

### 5.2 Diagnostics

```text
cn-health doctor [--json]
```

The command reports the CLI version, data directory, configured default
Registry, and starter Dataset state. It exits successfully only when every
required check passes. It does not require network access after initialization.

### 5.3 Laboratory Queries

```text
cn-health laboratory search QUERY [--limit N] [--json]
cn-health laboratory get CODE [--json]
```

Search uses the existing literal trigram and bigram behavior, accepts limits
from 1 through 200, and requires at least two Unicode characters. Output uses
the existing stable search envelope. A laboratory item exposes:

```text
code, system, terminologyVersion, displayZh, category, specimen,
resultType, ucumUnit, status
```

The source curation note and source provenance columns are not part of the
default runtime result.

## 6. Runtime Compatibility

The runtime MUST parse `runtime.minimumCliVersion` from every Manifest and
reject installation when the running semantic version is lower. Invalid
semantic versions fail closed. The 0.2.0 runtime continues to accept Manifest
schema version 1.

Compatibility failure uses error code `CLI_VERSION_INCOMPATIBLE` in JSON mode
and a distinct non-zero exit status.

## 7. Native and npm Releases

Release automation builds and tests at least:

```text
linux-x64
macos-x64
macos-arm64
windows-x64
```

Each native archive contains the CLI binary, `LICENSE`, and data notice. The
`cn-health` npm launcher declares matching optional platform packages. Platform
packages contain only the appropriate native binary and package metadata.

Publishing is tag-driven. CI may build package archives without publishing when
registry credentials are unavailable; an npm publish job requires an explicit
secret and never publishes from pull-request code.

## 8. Contributor Bootstrap

`scripts/bootstrap-dev.sh` MUST:

1. verify the documented development tools;
2. install locked Python dependencies;
3. validate Dataset Contracts;
4. build the Rust runtime;
5. initialize the public starter profile; and
6. run a real laboratory query.

The script fails on the first unsuccessful stage and does not acquire any
private Dataset source.

## 9. Verification

The implementation is complete when CI proves:

- Manifest minimum CLI compatibility accepts equal/older versions and rejects
  newer or invalid versions;
- laboratory exact lookup, trigram search, bigram search, pagination metadata,
  and JSON errors;
- signed Registry initialization, idempotent repeat initialization, tampered
  Registry rejection, and offline `doctor`/query after installation;
- npm packaged-binary resolution;
- release archives for every supported target; and
- the top-level quick start returns a real laboratory record.

## 10. Non-Goals

- A web UI or general HTTP query service.
- Public redistribution of any currently ineligible Dataset.
- Automatic discovery or downloading of government source workbooks.
- Treating the starter catalog as the complete official LOINC Chinese package.
- Committing local build caches, source snapshots, or the existing `dist/`
  Candidates.
