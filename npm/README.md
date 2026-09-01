# npm Distribution

Contains the thin npm wrapper around prebuilt `cn-health` native binaries. The
wrapper only resolves a platform binary and forwards arguments, stdio, signals,
and exit status; it does not reimplement runtime behavior.

Tag builds package Linux x64, macOS x64/arm64, and Windows x64 binaries. npm
publishing is separately gated by repository configuration and credentials.
