import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cn_health_compiler.core.source import SourceIntegrityError
from cn_health_compiler.sources.nhc_lab.build import build_nhc_laboratory_candidate
from cn_health_compiler.sources.nhc_lab.records import (
    NHCClinicalLabFormatError,
    iter_nhc_laboratory_records,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPO_ROOT / "tmp/WST_886—2026.md"
SOURCE_SHA256 = "a7f5e038dba32730a61437297c918c073b347304dc09ed6f6844025b2137bb8c"
HAS_REAL_SOURCE = SOURCE.is_file()


@pytest.mark.skipif(not HAS_REAL_SOURCE, reason="pinned local WS/T 886 source unavailable")
def test_real_wst_886_source_has_all_399_valid_records() -> None:
    records = list(
        iter_nhc_laboratory_records(
            SOURCE,
            source_version="2026",
            source_sha256=SOURCE_SHA256,
        )
    )

    assert len(records) == 399
    assert len({record.code for record in records}) == 399
    assert records[0].code == "0100101A"
    assert records[0].name == "白细胞计数"
    assert records[68].code == "1100301A"
    assert records[-1].code == "3400313B"
    assert records[-1].source_location == "表 1/序号 399"
    assert {record.scale_code for record in records} == {"A", "B", "C", "D"}


@pytest.mark.skipif(not HAS_REAL_SOURCE, reason="pinned local WS/T 886 source unavailable")
def test_real_candidate_builds_searchable_deterministic_sqlite(tmp_path: Path) -> None:
    build = build_nhc_laboratory_candidate(
        REPO_ROOT,
        SOURCE,
        tmp_path,
        git_commit="1" * 40,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    manifest = json.loads(build.manifest_path.read_text(encoding="utf-8"))
    assert manifest["release"]["id"] == "nhc-lab-tests@2026.r1"
    assert manifest["canonical"]["recordCount"] == 399
    assert manifest["sources"][0]["sha256"] == SOURCE_SHA256

    with sqlite3.connect(build.release_dir / "data.sqlite") as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA application_id").fetchone() == (0x434E4844,)
        assert connection.execute("SELECT count(*) FROM laboratory_test").fetchone() == (399,)
        assert connection.execute(
            "SELECT name, specimen_name, scale_name FROM laboratory_test WHERE code = ?",
            ("0100101A",),
        ).fetchone() == ("白细胞计数", "全血", "定量")
        assert connection.execute(
            "SELECT count(*) FROM laboratory_test_search_bigram WHERE term = '白细'"
        ).fetchone()[0] >= 1


@pytest.mark.skipif(not HAS_REAL_SOURCE, reason="pinned local WS/T 886 source unavailable")
def test_parser_rejects_appendix_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "bad.md"
    source.write_text(
        SOURCE.read_text(encoding="utf-8").replace(
            "<td>0100101A</td><td>白细胞计数</td><td>血细胞分析</td>",
            "<td>0100101A</td><td>白细胞计数</td><td>凝血实验</td>",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(NHCClinicalLabFormatError, match="appendix A.2"):
        list(
            iter_nhc_laboratory_records(
                source,
                source_version="2026",
                source_sha256="0" * 64,
            )
        )


@pytest.mark.skipif(not HAS_REAL_SOURCE, reason="pinned local WS/T 886 source unavailable")
def test_candidate_rejects_source_hash_mismatch(tmp_path: Path) -> None:
    changed = tmp_path / SOURCE.name
    changed.write_bytes(SOURCE.read_bytes() + b"\n")
    with pytest.raises(SourceIntegrityError, match="source SHA256 mismatch"):
        build_nhc_laboratory_candidate(
            REPO_ROOT,
            changed,
            tmp_path / "out",
            git_commit="1" * 40,
        )


def test_parser_concatenates_repeated_cross_page_table_headers(tmp_path: Path) -> None:
    source = tmp_path / "fixture.md"
    source.write_text(
        """# WS/T 886—2026
# 临床检验常用项目名称及代码
2026 - 05 - 25 发布
2026 - 11 - 01 实施
<table><tr><td>序号</td><td>代码</td><td>检验项目名称</td><td>类别</td><td>分析物</td><td>标本类型</td><td>标度</td></tr>
<tr><td>1</td><td>0100101A</td><td>白细胞计数</td><td>血细胞分析</td><td>白细胞(数量)</td><td>全血</td><td>定量</td></tr></table>
<table><tr><td>序号</td><td>代码</td><td>检验项目名称</td><td>类别</td><td>分析物</td><td>标本类型</td><td>标度</td></tr>
<tr><td>2</td><td>0100201A</td><td>红细胞计数</td><td>血细胞分析</td><td>红细胞(数量)</td><td>全血</td><td>定量</td></tr></table>
<table><tr><td>代码</td><td>临床检验常用项目的类别</td></tr><tr><td>01</td><td>血细胞分析</td></tr></table>
<table><tr><td>代码</td><td>临床检验常用项目的标本类型</td></tr><tr><td>01</td><td>全血</td></tr></table>
<table><tr><td>代码</td><td>标度</td></tr><tr><td>A</td><td>定量</td></tr></table>
""",
        encoding="utf-8",
    )

    records = list(
        iter_nhc_laboratory_records(
            source,
            source_version="2026",
            source_sha256="a" * 64,
        )
    )

    assert [record.code for record in records] == ["0100101A", "0100201A"]
    assert [record.source_location for record in records] == ["表 1/序号 1", "表 1/序号 2"]
