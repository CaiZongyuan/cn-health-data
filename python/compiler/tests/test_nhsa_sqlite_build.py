import hashlib
import sqlite3
from pathlib import Path

import pytest
from _nhsa import drug_record, validation_rules
from cn_health_compiler.sources.nhsa_drugs.sqlite import build_drug_sqlite
from cn_health_compiler.sources.nhsa_drugs.validation import DrugValidationError

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_build_drug_sqlite_creates_deterministic_searchable_artifact(tmp_path: Path) -> None:
    output_path = tmp_path / "data.sqlite"

    artifact = build_drug_sqlite(
        records=[drug_record("XA02", 3), drug_record("XA01", 2)],
        rules=validation_rules(),
        schema_path=REPO_ROOT / "datasets/nhsa-drugs/schema.sql",
        output_path=output_path,
    )

    assert artifact.path == output_path
    assert artifact.record_count == 2
    assert artifact.sha256 == hashlib.sha256(output_path.read_bytes()).hexdigest()
    assert artifact.size_bytes == output_path.stat().st_size
    assert artifact.validation.record_count == 2
    assert not list(tmp_path.glob("data.sqlite-*"))

    connection = sqlite3.connect(f"file:{output_path}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT code FROM drug ORDER BY rowid").fetchall() == [
            ("XA01",),
            ("XA02",),
        ]
        assert connection.execute(
            "SELECT count(*) FROM drug_fts WHERE drug_fts MATCH ?", ("二甲双胍",)
        ).fetchone() == (2,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA application_id").fetchone() == (0x434E4844,)
        assert connection.execute("PRAGMA user_version").fetchone() == (1,)
    finally:
        connection.close()


def test_build_drug_sqlite_removes_temporary_artifact_on_validation_error(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "data.sqlite"

    with pytest.raises(DrugValidationError, match="duplicate code XA01"):
        build_drug_sqlite(
            records=[drug_record("XA01", 2), drug_record("XA01", 3)],
            rules=validation_rules(),
            schema_path=REPO_ROOT / "datasets/nhsa-drugs/schema.sql",
            output_path=output_path,
        )

    assert not output_path.exists()
    assert not list(tmp_path.iterdir())
