# cn-health runtime package

This Cargo package implements the native local runtime. It treats local
Candidates as untrusted inputs, verifies compressed and uncompressed hashes,
checks SQLite integrity/application ID, and atomically updates `current.json`.
