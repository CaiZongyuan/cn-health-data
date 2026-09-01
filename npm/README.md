# npm Distribution

Contains the published `cn-health` launcher and platform-package manifests for
prebuilt native binaries. The wrapper only resolves a platform binary and
forwards arguments, stdio, signals, and exit status; it does not reimplement
runtime behavior.

Tag builds package Linux x64, macOS x64/arm64, and Windows x64 binaries. The
resumable publish script skips immutable versions already present in npm and
publishes the launcher only after all platform packages are available.
