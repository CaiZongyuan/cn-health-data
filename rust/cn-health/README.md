# cn-health runtime package

This Cargo package implements the native local runtime. It treats local
Candidates as untrusted inputs, verifies compressed and uncompressed hashes,
checks SQLite integrity/application ID, and atomically updates `current.json`.
Remote installation additionally verifies an Ed25519 Registry signature,
Manifest digest, release eligibility, URL origin, and bounded response sizes.
