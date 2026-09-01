"""Synthetic complete-package fixtures for LOINC compiler tests."""

import csv
import hashlib
import io
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE_VERSION = "fixture-1"

CORE_MEMBER = "LoincTable/Loinc.csv"
TRANSLATION_MEMBER = "LinguisticVariants/zh-CN.csv"
UNIT_MEMBER = "AccessoryFiles/Units.csv"
PART_MEMBER = "AccessoryFiles/Parts.csv"
SPECIMEN_MEMBER = "AccessoryFiles/PartLinks.csv"
PANEL_MEMBER = "AccessoryFiles/Panels.csv"
LICENSE_MEMBER = "LoincLicense_fixture.txt"


@dataclass(frozen=True, slots=True)
class LoincFixture:
    repo_root: Path
    core_archive: Path
    translation_archive: Path | None


def fixture_repository(
    root: Path,
    *,
    member_overrides: dict[str, bytes] | None = None,
    extra_core_members: dict[str, bytes] | None = None,
    package_mode: str = "split",
) -> LoincFixture:
    if package_mode not in {"combined", "split"}:
        raise ValueError(f"unsupported fixture package mode {package_mode!r}")
    dataset_dir = root / "datasets/loinc-zh-cn"
    schema_dir = root / "schemas"
    source_dir = root / "tmp"
    dataset_dir.mkdir(parents=True)
    schema_dir.mkdir()
    source_dir.mkdir()
    shutil.copyfile(REPO_ROOT / "datasets/loinc-zh-cn/schema.sql", dataset_dir / "schema.sql")
    shutil.copyfile(REPO_ROOT / "schemas/dataset.schema.json", schema_dir / "dataset.schema.json")
    shutil.copyfile(REPO_ROOT / "schemas/manifest.schema.json", schema_dir / "manifest.schema.json")
    (root / "uv.lock").write_text("synthetic fixture lock\n", encoding="utf-8")
    (root / "FIXTURE-RIGHTS.md").write_text(
        "Project-generated synthetic test records.\n", encoding="utf-8"
    )
    (dataset_dir / "LOINC_short_license.txt").write_text(
        "Synthetic fixture short license.\n", encoding="utf-8"
    )

    members = _source_members()
    members.update(member_overrides or {})
    core_archive = source_dir / "loinc-core.zip"
    translation_archive = source_dir / "loinc-zh-cn.zip"
    core_members = {
        CORE_MEMBER: members[CORE_MEMBER],
        UNIT_MEMBER: members[UNIT_MEMBER],
        PART_MEMBER: members[PART_MEMBER],
        SPECIMEN_MEMBER: members[SPECIMEN_MEMBER],
        PANEL_MEMBER: members[PANEL_MEMBER],
        LICENSE_MEMBER: members[LICENSE_MEMBER],
        **(extra_core_members or {}),
    }
    if package_mode == "combined":
        core_members[TRANSLATION_MEMBER] = members[TRANSLATION_MEMBER]
    _write_zip(core_archive, core_members)
    if package_mode == "split":
        _write_zip(translation_archive, {TRANSLATION_MEMBER: members[TRANSLATION_MEMBER]})

    layout = _layout(members, package_mode)
    (dataset_dir / "layout.yaml").write_text(
        yaml.safe_dump(layout, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    contract = _contract(
        core_archive,
        translation_archive if package_mode == "split" else core_archive,
        package_mode,
    )
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
    return LoincFixture(
        root,
        core_archive,
        translation_archive if package_mode == "split" else None,
    )


def source_members() -> dict[str, bytes]:
    return _source_members()


def csv_bytes(headers: tuple[str, ...], rows: list[tuple[str, ...]], *, bom: bool = False) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(headers)
    writer.writerows(rows)
    value = output.getvalue().encode("utf-8")
    return b"\xef\xbb\xbf" + value if bom else value


def _source_members() -> dict[str, bytes]:
    core_headers = (
        "LOINC_NUM",
        "COMPONENT",
        "PROPERTY",
        "TIME_ASPCT",
        "SYSTEM",
        "SCALE_TYP",
        "METHOD_TYP",
        "LONG_COMMON_NAME",
        "SHORTNAME",
        "CONSUMER_NAME",
        "CLASS",
        "CLASSTYPE",
        "ORDER_OBS",
        "STATUS",
        "STATUS_REASON",
        "STATUS_TEXT",
        "CHNG_TYPE",
        "DEFINITIONDESCRIPTION",
        "VersionFirstReleased",
        "VersionLastChanged",
        "PANELTYPE",
        "COMMON_TEST_RANK",
        "NOTICE",
    )
    core_rows = [
        (
            "1000-0",
            "Synthetic panel",
            "-",
            "Pt",
            "Bld",
            "Set",
            "",
            "Synthetic blood panel",
            "Synthetic panel",
            "Synthetic panel",
            "PANEL.CHEM",
            "1",
            "Order",
            "ACTIVE",
            "",
            "",
            "ADD",
            "Synthetic panel, generated for tests",
            "1.0",
            "1.0",
            "Panel",
            "10",
            "fixture-only",
        ),
        (
            "1001-8",
            "Synthetic analyte",
            "MCnc",
            "Pt",
            "Bld",
            "Qn",
            "",
            "Synthetic analyte in Blood",
            "Synthetic analyte",
            "Synthetic analyte",
            "CHEM",
            "1",
            "Both",
            "ACTIVE",
            "",
            "",
            "ADD",
            "Synthetic quantity",
            "1.0",
            "1.0",
            "",
            "20",
            "fixture-only",
        ),
        (
            "1002-6",
            "Synthetic cells",
            "NCnc",
            "Pt",
            "Bld",
            "Qn",
            "Auto",
            "Synthetic cells in Blood by Automated count",
            "Synthetic cells",
            "Synthetic cells",
            "HEM",
            "1",
            "Observation",
            "DEPRECATED",
            "Fixture lifecycle",
            "Synthetic inactive record",
            "DEL",
            "Synthetic inactive quantity",
            "1.0",
            "1.1",
            "",
            "30",
            "fixture-only",
        ),
    ]
    return {
        CORE_MEMBER: csv_bytes(core_headers, core_rows, bom=True),
        TRANSLATION_MEMBER: csv_bytes(
            (
                "LOINC_NUM",
                "COMPONENT",
                "PROPERTY",
                "TIME_ASPCT",
                "SYSTEM",
                "SCALE_TYP",
                "METHOD_TYP",
                "LANGUAGE",
                "TARGET_VERSION",
                "NOTE",
            ),
            [
                (
                    "1001-8",
                    "合成分析物",
                    "质量浓度",
                    "时间点",
                    "血液",
                    "定量",
                    "",
                    "zh-CN",
                    SOURCE_VERSION,
                    "fixture-only",
                ),
                (
                    "1002-6",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "zh-CN",
                    SOURCE_VERSION,
                    "missing translation",
                ),
            ],
            bom=True,
        ),
        UNIT_MEMBER: csv_bytes(
            ("LOINC_NUM", "UCUM", "SOURCE_VERSION", "NOTE"),
            [
                ("1001-8", "mg/dL;mg/dL;mm[Hg]", SOURCE_VERSION, "three examples"),
                ("1002-6", "10*9/L", SOURCE_VERSION, "one example"),
            ],
        ),
        PART_MEMBER: csv_bytes(
            ("PART_NUM", "PART_NAME", "PART_DISPLAY", "PART_TYPE", "STATUS"),
            [
                ("LP-SYS-1", "Blood", "Blood specimen", "SYSTEM", "ACTIVE"),
                ("LP-COMP-1", "Synthetic analyte", "", "COMPONENT", "ACTIVE"),
            ],
        ),
        SPECIMEN_MEMBER: csv_bytes(
            ("LOINC_NUM", "PART_NUM", "LINK_TYPE", "PART_TYPE"),
            [
                ("1001-8", "LP-SYS-1", "Primary", "SYSTEM"),
                ("1001-8", "LP-COMP-1", "Primary", "COMPONENT"),
            ],
        ),
        PANEL_MEMBER: csv_bytes(
            (
                "PARENT_ID",
                "MEMBER_ID",
                "PANEL_LOINC_NUM",
                "MEMBER_LOINC_NUM",
                "SEQUENCE",
                "RELATIONSHIP",
                "MEMBER_TYPE",
                "CARDINALITY",
            ),
            [
                (
                    "root-1",
                    "root-1",
                    "1000-0",
                    "1000-0",
                    "0",
                    "COMPONENT",
                    "LOINC",
                    "1..1",
                ),
                (
                    "parent-1",
                    "member-1",
                    "1000-0",
                    "1001-8",
                    "1",
                    "COMPONENT",
                    "LOINC",
                    "1..1",
                ),
                (
                    "parent-1",
                    "external-1",
                    "ignored",
                    "external",
                    "2",
                    "ANSWER",
                    "EXTERNAL",
                    "0..*",
                ),
            ],
        ),
        LICENSE_MEMBER: b"Synthetic fixture license\n",
    }


def _member_contract(
    archive: str, path: str, content: bytes, headers: list[str]
) -> dict[str, object]:
    return {
        "archive": archive,
        "member": path,
        "uncompressed_sha256": hashlib.sha256(content).hexdigest(),
        "uncompressed_size_bytes": len(content),
        "encoding": "utf-8-sig" if content.startswith(b"\xef\xbb\xbf") else "utf-8",
        "delimiter": ",",
        "headers": headers,
    }


def _layout(members: dict[str, bytes], package_mode: str) -> dict[str, object]:
    core_headers = next(csv.reader(io.StringIO(members[CORE_MEMBER].decode("utf-8-sig"))))
    translation_headers = next(
        csv.reader(io.StringIO(members[TRANSLATION_MEMBER].decode("utf-8-sig")))
    )
    unit_headers = next(csv.reader(io.StringIO(members[UNIT_MEMBER].decode("utf-8"))))
    part_headers = next(csv.reader(io.StringIO(members[PART_MEMBER].decode("utf-8"))))
    specimen_headers = next(csv.reader(io.StringIO(members[SPECIMEN_MEMBER].decode("utf-8"))))
    panel_headers = next(csv.reader(io.StringIO(members[PANEL_MEMBER].decode("utf-8"))))
    return {
        "version": 1,
        "package_mode": package_mode,
        "archive_limits": {
            "maximum_entry_count": 20,
            "maximum_total_uncompressed_bytes": 1_000_000,
            "maximum_member_uncompressed_bytes": 500_000,
            "maximum_compression_ratio": 100,
            "allowed_compression": ["deflate"],
        },
        "license": {
            "archive": "core",
            "member": LICENSE_MEMBER,
            "uncompressed_sha256": hashlib.sha256(members[LICENSE_MEMBER]).hexdigest(),
            "uncompressed_size_bytes": len(members[LICENSE_MEMBER]),
        },
        "core": {
            **_member_contract("core", CORE_MEMBER, members[CORE_MEMBER], core_headers),
            "columns": {
                "code": "LOINC_NUM",
                "component": "COMPONENT",
                "property": "PROPERTY",
                "time_aspect": "TIME_ASPCT",
                "system": "SYSTEM",
                "scale_type": "SCALE_TYP",
                "method_type": "METHOD_TYP",
                "long_common_name": "LONG_COMMON_NAME",
                "short_name": "SHORTNAME",
                "consumer_name": "CONSUMER_NAME",
                "class": "CLASS",
                "class_type": "CLASSTYPE",
                "order_obs": "ORDER_OBS",
                "status": "STATUS",
                "status_reason": "STATUS_REASON",
                "status_text": "STATUS_TEXT",
                "change_type": "CHNG_TYPE",
                "definition_description": "DEFINITIONDESCRIPTION",
                "version_first_released": "VersionFirstReleased",
                "version_last_changed": "VersionLastChanged",
                "panel_type": "PANELTYPE",
            },
            "preserved_metadata": {"commonTestRank": "COMMON_TEST_RANK"},
            "ignored_columns": {"NOTICE": "fixture source notice is package metadata"},
        },
        "linguistic_variant": {
            **_member_contract(
                "linguistic-variant" if package_mode == "split" else "core",
                TRANSLATION_MEMBER,
                members[TRANSLATION_MEMBER],
                translation_headers,
            ),
            "code_column": "LOINC_NUM",
            "display_from_columns": [
                "COMPONENT",
                "PROPERTY",
                "TIME_ASPCT",
                "SYSTEM",
                "SCALE_TYP",
                "METHOD_TYP",
            ],
            "preserved_metadata": {
                "component": "COMPONENT",
                "property": "PROPERTY",
                "timeAspect": "TIME_ASPCT",
                "system": "SYSTEM",
                "scaleType": "SCALE_TYP",
                "methodType": "METHOD_TYP",
            },
            "filters": {"LANGUAGE": "zh-CN", "TARGET_VERSION": SOURCE_VERSION},
            "ignored_columns": {"NOTE": "fixture row note"},
        },
        "units": [
            {
                **_member_contract("core", UNIT_MEMBER, members[UNIT_MEMBER], unit_headers),
                "code_column": "LOINC_NUM",
                "unit_column": "UCUM",
                "unit_kind": "example",
                "separator": ";",
                "filters": {"SOURCE_VERSION": SOURCE_VERSION},
                "ignored_columns": {"NOTE": "fixture row note"},
            }
        ],
        "parts": {
            **_member_contract("core", PART_MEMBER, members[PART_MEMBER], part_headers),
            "part_number_column": "PART_NUM",
            "part_name_column": "PART_NAME",
            "part_display_name_column": "PART_DISPLAY",
            "filters": {"PART_TYPE": "SYSTEM"},
            "ignored_columns": {"STATUS": "not needed for specimen candidate link"},
        },
        "specimen_links": {
            **_member_contract("core", SPECIMEN_MEMBER, members[SPECIMEN_MEMBER], specimen_headers),
            "code_column": "LOINC_NUM",
            "part_number_column": "PART_NUM",
            "link_type_column": "LINK_TYPE",
            "filters": {"PART_TYPE": "SYSTEM"},
        },
        "panel_members": {
            **_member_contract("core", PANEL_MEMBER, members[PANEL_MEMBER], panel_headers),
            "parent_id_column": "PARENT_ID",
            "member_id_column": "MEMBER_ID",
            "panel_code_column": "PANEL_LOINC_NUM",
            "member_code_column": "MEMBER_LOINC_NUM",
            "member_order_column": "SEQUENCE",
            "relationship_column": "RELATIONSHIP",
            "exclude_self_links": True,
            "filters": {"MEMBER_TYPE": "LOINC"},
            "preserved_metadata": {"cardinality": "CARDINALITY"},
        },
    }


def _contract(
    core_archive: Path,
    translation_archive: Path,
    package_mode: str,
) -> dict[str, object]:
    return {
        "id": "loinc-zh-cn",
        "title": "合成 LOINC 中文完整包测试",
        "description": "Project-generated synthetic LOINC package fixture.",
        "status": "experimental",
        "dataset_schema_version": 2,
        "authority": {
            "name": "CN Health Data test fixtures",
            "role": "project-generated-fixture",
            "verification": "fixture-reviewed",
        },
        "source": {
            "type": "composite-zip",
            "acquisition": "manual-local",
            "package_mode": package_mode,
            "declared_version": SOURCE_VERSION,
            "upstream_sync": False,
            "core": _archive_source(core_archive, SOURCE_VERSION, "core"),
            "linguistic_variant": {
                **_archive_source(translation_archive, SOURCE_VERSION, "linguistic-variant"),
                "target_version": SOURCE_VERSION,
            },
        },
        "versioning": {"strategy": "upstream-version"},
        "output": {"primary": "sqlite", "optional": ["parquet"]},
        "runtime": {"searchable": True, "minimum_sqlite_version": "3.38.0"},
        "rights": {
            "redistribution": "private",
            "release_eligible": False,
            "basis": "Project-generated synthetic fixture",
            "evidence": ["FIXTURE-RIGHTS.md"],
            "attribution": "CN Health Data test fixtures",
            "reviewed_by": "fixture-maintainer",
            "reviewed_at": "2026-09-01",
            "allowed_artifact_types": ["sqlite", "sqlite-zstd", "parquet"],
        },
        "validation": {
            "expected_loinc_count": 3,
            "expected_unit_count": 4,
            "expected_specimen_count": 1,
            "expected_panel_member_count": 1,
            "expected_source_member_rows": {
                "core": 3,
                "linguistic-variant": 2,
                "unit:example": 2,
                "parts": 2,
                "specimen-links": 2,
                "panel-members": 3,
            },
            "allowed_statuses": ["ACTIVE", "DEPRECATED"],
            "allowed_order_obs": ["Order", "Both", "Observation"],
            "allowed_unit_kinds": ["example"],
            "allowed_specimen_link_types": ["Primary"],
            "allowed_panel_relationships": ["COMPONENT"],
            "record_count": {
                "max_relative_decrease": 0.1,
                "max_relative_increase": 0.1,
            },
        },
    }


def _archive_source(path: Path, version: str, role: str) -> dict[str, object]:
    return {
        "authority": "CN Health Data test fixtures",
        "authority_role": role,
        "format": "zip",
        "acquisition": "manual-local",
        "original_filename": path.name,
        "path_hint": f"tmp/{path.name}",
        "source_url": f"https://example.test/{path.name}",
        "declared_version": version,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
        "source_reacquirable": False,
    }


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
