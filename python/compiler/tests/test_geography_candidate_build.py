import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import polars as pl
import yaml
import zstandard
from cn_health_compiler.cli import app
from cn_health_compiler.sources.geography.build import build_geography_candidate
from jsonschema import Draft202012Validator, FormatChecker
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_zip(path: Path, lines: list[str]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("readme.txt", "Synthetic fixture\n")
        archive.writestr("CN.txt", "\n".join(lines) + "\n")


def _place_line(
    geoname_id: str,
    name: str,
    feature_class: str,
    feature_code: str,
    population: str,
) -> str:
    return "\t".join(
        [
            geoname_id,
            name,
            name,
            "",
            "31.865",
            "120.5389",
            feature_class,
            feature_code,
            "CN",
            "",
            "04",
            "3205",
            "",
            "",
            population,
            "",
            "5",
            "Asia/Shanghai",
            "2026-08-29",
        ]
    )


def _fixture_repository(root: Path) -> tuple[Path, Path, Path]:
    dataset_dir = root / "datasets/geography-cn"
    schema_dir = root / "schemas"
    source_dir = root / "tmp"
    dataset_dir.mkdir(parents=True)
    schema_dir.mkdir()
    source_dir.mkdir()
    shutil.copyfile(REPO_ROOT / "datasets/geography-cn/schema.sql", dataset_dir / "schema.sql")
    shutil.copyfile(REPO_ROOT / "schemas/manifest.schema.json", schema_dir / "manifest.schema.json")
    (root / "uv.lock").write_text("fixture lock\n", encoding="utf-8")
    (dataset_dir / "layout.yaml").write_text("version: 1\n", encoding="utf-8")

    gazetteer = source_dir / "geonames.zip"
    postal = source_dir / "postal.zip"
    divisions = source_dir / "divisions.csv"
    _write_zip(
        gazetteer,
        [
            _place_line("1806260", "江苏省", "A", "ADM1", "0"),
            _place_line("1787331", "张家港市", "P", "PPLA3", "1432044"),
        ],
    )
    _write_zip(
        postal,
        [
            "\t".join(
                [
                    "CN",
                    "215600",
                    "张家港市",
                    "江苏省",
                    "04",
                    "苏州市",
                    "3205",
                    "张家港市",
                    "",
                    "31.865",
                    "120.5389",
                    "4",
                ]
            )
        ],
    )
    divisions.write_text(
        "id,pid,deep,name,pinyin_prefix,pinyin,ext_id,ext_name\n"
        '32,0,0,"江苏","j","jiang su","320000000000","江苏省"\n'
        '3205,32,1,"苏州","s","su zhou","320500000000","苏州市"\n',
        encoding="utf-8-sig",
    )

    sources = {
        "gazetteer": gazetteer,
        "postal": postal,
        "divisions": divisions,
    }
    source_contract = {
        key: {
            "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
        }
        for key, path in sources.items()
    }
    contract = {
        "id": "geography-cn",
        "title": "测试中国地理数据",
        "description": "Synthetic multi-source geography fixture.",
        "status": "experimental",
        "authority": {
            "name": "测试来源集合",
            "role": "source-collection",
            "verification": "fixture",
        },
        "source": {
            "type": "composite",
            "acquisition": "manual-local",
            "declared_version": "2026-08-29",
            **source_contract,
            "upstream_sync": False,
        },
        "versioning": {"strategy": "declared-source-version"},
        "output": {"primary": "sqlite", "optional": ["parquet"]},
        "runtime": {"searchable": True, "minimum_sqlite_version": "3.34.0"},
        "rights": {"redistribution": "review-required", "release_eligible": False},
        "validation": {
            "min_division_count": 2,
            "min_place_count": 2,
            "min_postal_count": 1,
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
    return gazetteer, divisions, postal


def test_build_geography_candidate_packages_three_sources(tmp_path: Path) -> None:
    gazetteer, divisions, postal = _fixture_repository(tmp_path)

    result = build_geography_candidate(
        repo_root=tmp_path,
        gazetteer_path=gazetteer,
        division_path=divisions,
        postal_path=postal,
        output_root=tmp_path / "dist",
        git_commit="d" * 40,
        created_at=datetime(2026, 8, 29, tzinfo=UTC),
    )

    release = result.release_dir
    assert sorted(path.name for path in release.iterdir()) == [
        "administrative-divisions.parquet",
        "data.sqlite",
        "data.sqlite.zst",
        "diff.json",
        "manifest.json",
        "places.parquet",
        "postal-areas.parquet",
        "validation.json",
    ]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    schema = json.loads((tmp_path / "schemas/manifest.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    assert manifest["release"]["id"] == "geography-cn@2026-08-29.r1"
    assert manifest["canonical"]["recordCount"] == 5
    assert [source["role"] for source in manifest["sources"]] == [
        "administrative-divisions",
        "gazetteer",
        "postal-areas",
    ]
    assert pl.read_parquet(release / "administrative-divisions.parquet").height == 2
    assert pl.read_parquet(release / "places.parquet").height == 2
    assert pl.read_parquet(release / "postal-areas.parquet").height == 1
    sqlite_bytes = (release / "data.sqlite").read_bytes()
    assert (
        zstandard.ZstdDecompressor().decompress((release / "data.sqlite.zst").read_bytes())
        == sqlite_bytes
    )
    connection = sqlite3.connect(f"file:{release / 'data.sqlite'}?mode=ro", uri=True)
    try:
        assert connection.execute("SELECT count(*) FROM administrative_division").fetchone() == (2,)
    finally:
        connection.close()

    revision = build_geography_candidate(
        repo_root=tmp_path,
        gazetteer_path=gazetteer,
        division_path=divisions,
        postal_path=postal,
        output_root=tmp_path / "dist",
        build_revision=2,
        sequence=2,
        base_release_dir=release,
        git_commit="d" * 40,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    revision_manifest = json.loads(revision.manifest_path.read_text(encoding="utf-8"))
    revision_diff = json.loads((revision.release_dir / "diff.json").read_text(encoding="utf-8"))
    assert revision_manifest["release"]["supersedes"] == "geography-cn@2026-08-29.r1"
    assert revision_diff["unchanged"] == 5
    assert revision_diff["added"] == revision_diff["removed"] == 0


def test_build_command_accepts_all_geography_sources(tmp_path: Path) -> None:
    gazetteer, divisions, postal = _fixture_repository(tmp_path)

    result = CliRunner().invoke(
        app,
        [
            "build",
            "geography-cn",
            "--source",
            str(gazetteer),
            "--division-source",
            str(divisions),
            "--postal-source",
            str(postal),
            "--repo-root",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "geography-cn/releases/2026-08-29.r1/manifest.json" in result.output
