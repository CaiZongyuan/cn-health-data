from hashlib import sha256
from pathlib import Path

import pytest
from cn_health_compiler.core.source import SourceIntegrityError, snapshot_local_source


def test_snapshot_local_source_is_content_addressed(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    content = b"fixture workbook bytes"
    source.write_bytes(content)
    expected_sha256 = sha256(content).hexdigest()

    snapshot = snapshot_local_source(source, expected_sha256, tmp_path / "snapshots")

    assert snapshot.sha256 == expected_sha256
    assert snapshot.size_bytes == len(content)
    assert snapshot.original_filename == source.name
    assert snapshot.path == tmp_path / "snapshots" / expected_sha256 / "source.xlsx"
    assert snapshot.path.read_bytes() == content


def test_snapshot_local_source_rejects_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    source.write_bytes(b"unexpected")

    with pytest.raises(SourceIntegrityError, match="source SHA256 mismatch"):
        snapshot_local_source(source, "0" * 64, tmp_path / "snapshots")
