import gzip
import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import yaml
from cn_health_compiler.cli import app
from cn_health_compiler.sources.population.build import build_population_candidate
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]


def _fixture_repository(root: Path) -> Path:
    dataset_dir = root / "datasets/population-cn"
    schema_dir = root / "schemas"
    source_dir = root / "tmp"
    dataset_dir.mkdir(parents=True)
    schema_dir.mkdir()
    source_dir.mkdir()
    shutil.copyfile(REPO_ROOT / "datasets/population-cn/schema.sql", dataset_dir / "schema.sql")
    shutil.copyfile(REPO_ROOT / "schemas/manifest.schema.json", schema_dir / "manifest.schema.json")
    (root / "uv.lock").write_text("fixture lock\n", encoding="utf-8")
    (dataset_dir / "layout.yaml").write_text("version: 1\n", encoding="utf-8")
    source = source_dir / "wpp.csv.gz"
    header = (
        "SortOrder,LocID,Notes,ISO3_code,ISO2_code,SDMX_code,LocTypeID,LocTypeName,"
        "ParentID,Location,VarID,Variant,Time,MidPeriod,AgeGrp,AgeGrpStart,AgeGrpSpan,"
        "PopMale,PopFemale,PopTotal"
    )
    rows = (
        "134,156,5,CHN,CN,156,4,Country/Area,906,China,2,Medium,2026,2026.5,"
        "0-4,0,5,23.125,21.250,44.375\n"
        "134,156,5,CHN,CN,156,4,Country/Area,906,China,2,Medium,2026,2026.5,"
        "100+,100,-1,0.004,0.048,0.052\n"
    )
    with gzip.open(source, "wt", encoding="utf-8-sig", newline="") as stream:
        stream.write(header + "\n" + rows)
    source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    contract = {
        "id": "population-cn",
        "title": "测试中国人口分布",
        "description": "Synthetic WPP fixture.",
        "status": "experimental",
        "authority": {
            "name": "United Nations",
            "role": "original-authority",
            "verification": "fixture",
        },
        "source": {
            "type": "gzip-csv",
            "acquisition": "official-download",
            "path_hint": "tmp/wpp.csv.gz",
            "source_url": "https://example.test/wpp.csv.gz",
            "declared_version": "WPP2024",
            "sha256": source_sha256,
            "size_bytes": source.stat().st_size,
            "upstream_sync": False,
        },
        "versioning": {"strategy": "upstream-release"},
        "output": {"primary": "sqlite", "optional": ["parquet"]},
        "runtime": {"searchable": False, "minimum_sqlite_version": "3.34.0"},
        "rights": {"redistribution": "normalized-only", "release_eligible": False},
        "validation": {
            "expected_age_group_count": 2,
            "min_record_count": 2,
            "min_year_count": 1,
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


def test_population_candidate_and_cli_package_wpp_source(tmp_path: Path) -> None:
    source = _fixture_repository(tmp_path)

    result = build_population_candidate(
        repo_root=tmp_path,
        source_path=source,
        output_root=tmp_path / ".work/direct-dist",
        git_commit="d" * 40,
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["release"]["id"] == "population-cn@WPP2024.r1"
    assert manifest["canonical"]["recordCount"] == 2
    assert pl.read_parquet(result.release_dir / "data.parquet").height == 2

    cli_result = CliRunner().invoke(
        app,
        ["build", "population-cn", "--source", str(source), "--repo-root", str(tmp_path)],
    )

    assert cli_result.exit_code == 0, cli_result.output
    assert "population-cn/releases/WPP2024.r1/manifest.json" in cli_result.output
