"""Immutable local source snapshots."""

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import BinaryIO

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CHUNK_SIZE = 1024 * 1024


class SourceIntegrityError(ValueError):
    """Raised when source bytes do not match their declared identity."""


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """A verified, content-addressed source file."""

    path: Path
    sha256: str
    size_bytes: int
    original_filename: str


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    size_bytes = 0
    while chunk := stream.read(_CHUNK_SIZE):
        digest.update(chunk)
        size_bytes += len(chunk)
    return digest.hexdigest(), size_bytes


def hash_file(path: Path) -> tuple[str, int]:
    """Return the SHA256 and byte length of a file."""
    with path.open("rb") as stream:
        return _hash_stream(stream)


def snapshot_local_source(
    source_path: Path,
    expected_sha256: str,
    snapshots_dir: Path,
) -> SourceSnapshot:
    """Verify and atomically copy a local source into content-addressed storage."""
    if _SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise ValueError("expected_sha256 must be 64 lowercase hexadecimal characters")

    original_filename = source_path.name
    source_path = source_path.resolve(strict=True)
    if not source_path.is_file():
        raise FileNotFoundError(f"source is not a regular file: {source_path}")

    source_sha256, source_size = hash_file(source_path)
    if source_sha256 != expected_sha256:
        raise SourceIntegrityError(
            f"source SHA256 mismatch: expected {expected_sha256}, found {source_sha256}"
        )

    snapshot_dir = snapshots_dir / expected_sha256
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower()
    snapshot_path = snapshot_dir / f"source{suffix}"
    if snapshot_path.exists():
        snapshot_sha256, snapshot_size = hash_file(snapshot_path)
        if (snapshot_sha256, snapshot_size) != (expected_sha256, source_size):
            raise SourceIntegrityError(f"existing source snapshot is corrupt: {snapshot_path}")
    else:
        _copy_verified_source(source_path, snapshot_path, expected_sha256, source_size)

    return SourceSnapshot(
        path=snapshot_path,
        sha256=expected_sha256,
        size_bytes=source_size,
        original_filename=original_filename,
    )


def _copy_verified_source(
    source_path: Path,
    snapshot_path: Path,
    expected_sha256: str,
    expected_size: int,
) -> None:
    temporary_path: Path | None = None
    try:
        with (
            source_path.open("rb") as source,
            NamedTemporaryFile(
                mode="w+b",
                dir=snapshot_path.parent,
                prefix=".source-",
                delete=False,
            ) as temporary,
        ):
            temporary_path = Path(temporary.name)
            digest = hashlib.sha256()
            size_bytes = 0
            while chunk := source.read(_CHUNK_SIZE):
                temporary.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)
            temporary.flush()
            os.fsync(temporary.fileno())

        copied_sha256 = digest.hexdigest()
        if (copied_sha256, size_bytes) != (expected_sha256, expected_size):
            raise SourceIntegrityError("source changed while creating its snapshot")
        os.replace(temporary_path, snapshot_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
