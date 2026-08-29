# npm Distribution

Contains the thin npm wrapper around prebuilt `cn-health` native binaries. The
wrapper only resolves a platform binary and forwards arguments, stdio, signals,
and exit status; it does not reimplement runtime behavior.
