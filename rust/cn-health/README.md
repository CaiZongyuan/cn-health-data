# cn-health runtime package

This Cargo package implements the native local runtime. It treats local
Candidates as untrusted inputs, verifies compressed and uncompressed hashes,
checks SQLite integrity/application ID, and atomically updates `current.json`.
Remote installation additionally verifies an Ed25519 Registry signature,
Manifest digest, release eligibility, URL origin, and bounded response sizes.
Version 0.2.0 adds a pinned public starter Registry, idempotent `init`, offline
`doctor`, Manifest minimum CLI enforcement, and laboratory lookup/search.
Version 0.3.0 makes all seven implemented normalized Datasets the default
installation, adds `init --only`, and expands offline diagnostics across the
complete installed set.
Version 0.4.0 adds the WS/T 886 authority Dataset, schema v1/v2 laboratory
compatibility, adult reference/simulation metadata, and laboratory panel
search/expansion.
Version 0.5.0 adds exact signed-Registry Release materialization with verified,
atomic Manifest/SQLite output and a machine-readable consumer receipt.
Version 0.5.1 reports download, decompression, verification, and export progress
on stderr with TTY and piped rendering, keeping stdout output byte-identical.
