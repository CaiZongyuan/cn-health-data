import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import yaml
from cn_health_compiler.cli import app
from cn_health_compiler.sources.laboratory.build import build_laboratory_candidate
from cn_health_compiler.sources.laboratory.records import iter_laboratory_records
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]


def _fixture_repository(root: Path) -> Path:
    dataset_dir = root / "datasets/laboratory-cn"
    schema_dir = root / "schemas"
    source_dir = root / "tmp"
    dataset_dir.mkdir(parents=True)
    schema_dir.mkdir()
    source_dir.mkdir()
    shutil.copyfile(REPO_ROOT / "datasets/laboratory-cn/schema.sql", dataset_dir / "schema.sql")
    shutil.copyfile(REPO_ROOT / "schemas/manifest.schema.json", schema_dir / "manifest.schema.json")
    (root / "uv.lock").write_text("fixture lock\n", encoding="utf-8")
    (root / "LICENSE").write_text("Synthetic fixture license\n", encoding="utf-8")
    (dataset_dir / "layout.yaml").write_text("version: 1\n", encoding="utf-8")
    source = source_dir / "laboratory.csv"
    source.write_text(
        "code,display_zh,category,specimen,result_type,ucum_unit,loinc_version,status,source_note\n"
        "8310-5,体温,vital-sign,body,quantity,Cel,2.83,active,project-authored fixture\n"
        "4548-4,糖化血红蛋白,chemistry,blood,quantity,%,2.83,active,project-authored fixture\n",
        encoding="utf-8",
    )
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    contract = {
        "id": "laboratory-cn",
        "title": "测试中文检验目录",
        "description": "Project-authored synthetic laboratory catalog fixture.",
        "status": "experimental",
        "authority": {
            "name": "CN Health Data contributors",
            "role": "project-author",
            "verification": "fixture",
        },
        "source": {
            "type": "csv",
            "acquisition": "manual-local",
            "path_hint": "tmp/laboratory.csv",
            "source_url": "https://example.test/laboratory.csv",
            "declared_version": "2026-08-30",
            "sha256": source_sha256,
            "size_bytes": source.stat().st_size,
            "upstream_sync": False,
        },
        "versioning": {"strategy": "project-release"},
        "output": {"primary": "sqlite", "optional": ["parquet"]},
        "runtime": {"searchable": True, "minimum_sqlite_version": "3.34.0"},
        "rights": {
            "redistribution": "public",
            "release_eligible": True,
            "evidence": ["LICENSE"],
        },
        "validation": {
            "allowed_ucum_units": ["%", "Cel"],
            "expected_record_count": 2,
            "required_codes": ["8310-5", "4548-4"],
            "terminology_version": "2.83",
        },
    }
    (dataset_dir / "dataset.yaml").write_text(
        yaml.safe_dump(contract, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (root / ".gitignore").write_text("tmp/\n.work/\ndist/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main", root], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", root, "config", "user.email", "fixture@example.invalid"], check=True
    )
    subprocess.run(["git", "-C", root, "config", "user.name", "Fixture"], check=True)
    subprocess.run(["git", "-C", root, "add", "."], check=True)
    subprocess.run(["git", "-C", root, "commit", "-m", "fixture"], check=True, capture_output=True)
    return source


def test_laboratory_candidate_and_cli_package_project_catalog(tmp_path: Path) -> None:
    source = _fixture_repository(tmp_path)

    result = build_laboratory_candidate(
        repo_root=tmp_path,
        source_path=source,
        output_root=tmp_path / ".work/direct-dist",
        git_commit="d" * 40,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["release"]["id"] == "laboratory-cn@2026-08-30.r1"
    assert manifest["canonical"]["recordCount"] == 2
    assert manifest["rights"] == {
        "evidence": ["LICENSE"],
        "redistribution": "public",
        "releaseEligible": True,
    }
    assert pl.read_parquet(result.release_dir / "data.parquet").height == 2
    connection = sqlite3.connect(result.release_dir / "data.sqlite")
    try:
        assert connection.execute(
            "SELECT code, display_zh, terminology_version FROM laboratory_concept ORDER BY code"
        ).fetchall() == [
            ("4548-4", "糖化血红蛋白", "2.83"),
            ("8310-5", "体温", "2.83"),
        ]
    finally:
        connection.close()

    cli_result = CliRunner().invoke(
        app,
        ["build", "laboratory-cn", "--source", str(source), "--repo-root", str(tmp_path)],
    )
    assert cli_result.exit_code == 0, cli_result.output
    assert "laboratory-cn/releases/2026-08-30.r1/manifest.json" in cli_result.output


def test_project_catalog_contains_synthea_truth_critical_laboratory_codes() -> None:
    source = REPO_ROOT / "datasets/laboratory-cn/catalog.csv"
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    records = list(
        iter_laboratory_records(
            source,
            source_version="2026-08-30",
            source_sha256=source_sha256,
        )
    )

    assert len(records) == 18
    assert {"8310-5", "4548-4", "2339-0"}.issubset(record.code for record in records)
    assert all(record.display_zh for record in records)
