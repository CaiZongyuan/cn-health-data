# Full Public Distribution Specification

Status: Accepted for implementation  
Tracking: GitHub issue #10

## 1. Goal

Users install the complete set of implemented, normalized CN Health Data
Datasets directly from the project. They do not acquire private source files or
run the Python compiler.

The default path is:

```text
cn-health init
```

There are no public starter/open/full profiles. Selective installation is an
advanced option:

```text
cn-health init --only DATASET_ID[,DATASET_ID...]
```

## 2. Included Data

Default initialization installs these SQLite Datasets in stable order:

1. `geography-cn`
2. `laboratory-cn`
3. `loinc-zh-cn`
4. `names-cn`
5. `nhc-icd10-clinical`
6. `nhsa-drugs`
7. `population-cn`

`nhc-procedure-clinical` is excluded until its compiler exists. The current
Synthea CN profile is distributed separately because it is a resource tree, not
a runtime SQLite Dataset.

## 3. Publication Boundary

The public distribution contains only normalized, versioned artifacts:

- `data.sqlite.zst`, including the uncompressed SQLite hash and size;
- every declared Parquet export;
- license and attribution files declared by a Candidate;
- `manifest.json`, `validation.json`, and `diff.json`; and
- a signed Registry and its public key.

The public distribution excludes:

- uncompressed `data.sqlite` transport copies;
- raw XLSX, ZIP, PDF, CSV source packages, or authenticated downloads;
- `.work/`, source snapshots, caches, or logs;
- historical revisions that are not the currently recommended Release; and
- byte-identical duplicate revisions.

Removing the uncompressed transport artifact does not alter canonical data. The
`data.sqlite.zst` entry retains the exact uncompressed name, SHA256, and byte
size, and the runtime verifies those values during bounded decompression.

## 4. Provenance and Notices

Public availability, normalization, and non-commercial project status do not
replace source provenance. Every public Manifest keeps the factual source name,
authority role, version/date, original filename, source URL when known, SHA256,
record count, attribution, and rights evidence.

The project publishes no legal conclusion that third-party content is
repository-owned or public domain. Source-specific notices control over the MIT
software license. Corrections and takedown decisions use immutable Release IDs
and Registry revocation rather than deleting local user data without consent.

## 5. Distribution Layout

```text
distribution/
|-- registry.json
|-- registry.json.sig
|-- registry.pub
`-- releases/
    `-- DATASET_ID/
        `-- STORAGE_KEY/
            |-- manifest.json
            |-- data.sqlite.zst
            |-- *.parquet
            |-- validation.json
            |-- diff.json
            `-- declared license files
```

All declared Registry, signature, Manifest, report, and artifact URLs share the
same HTTPS origin. Every staged artifact must exist and match its declared hash
and size before the Registry is signed.

## 6. Runtime Contract

`cn-health init` installs all default Datasets. `--only` accepts a comma-delimited
list, removes duplicates while preserving canonical order, and rejects unknown
or empty Dataset IDs before network access.

Initialization remains resumable and idempotent. If one Dataset fails, already
verified installations remain intact; repeating the command verifies and skips
the same installed Releases.

Successful JSON output is:

```json
{
  "schemaVersion": 2,
  "command": "init",
  "selection": "all",
  "items": [
    {
      "datasetId": "geography-cn",
      "releaseId": "geography-cn@VERSION",
      "status": "installed"
    }
  ]
}
```

`selection` is `all` or `only`. Each item status is `installed` or
`already-installed`.

## 7. Diagnostics

`cn-health doctor` checks all eight default Dataset pointers, signed-Registry
trust metadata, installed SQLite presence, and representative exact lookups for
drug, diagnosis, LOINC, and laboratory query surfaces. The command remains
offline after installation.

## 8. Size Contract

The current latest compressed SQLite set is approximately 75.33 MiB. The
installed uncompressed SQLite set is approximately 784 MiB. Release automation
reports both totals from staged Manifests; documentation must not quote the
local multi-revision `dist/` size as a user download size.

## 9. Verification

Completion requires:

- all eight Contracts and staged Manifests are release-eligible;
- staged Manifests omit uncompressed SQLite transport entries;
- every remaining artifact and report exists and matches SHA256 and size;
- the signed Registry recommends exactly one current Release per Dataset;
- clean default and selective initialization pass against a loopback Registry;
- repeated initialization reports `already-installed`;
- installed drug, diagnosis, LOINC, and laboratory queries return real records;
- no public artifact contains or embeds a raw source file; and
- npm and native release smoke tests install the same public data.
