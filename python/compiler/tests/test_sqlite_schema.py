import sqlite3
from pathlib import Path

from cn_health_compiler.core.sqlite import apply_schema

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_nhsa_drug_schema_supports_chinese_substring_search() -> None:
    connection = sqlite3.connect(":memory:")
    apply_schema(connection, REPO_ROOT / "datasets" / "nhsa-drugs" / "schema.sql")
    connection.execute(
        """
        INSERT INTO drug VALUES (
            'XA01ABD075A002010100483', 'fixture', '盐酸二甲双胍片', '无',
            '片剂', '片剂', '0.5g', '0.5g', '铝塑', '10', '片', '盒',
            '测试企业', NULL, '测试企业', '国药准字TEST', NULL, '86900000000000',
            NULL, '上市', '二甲双胍', '乙', '口服常释剂型', '1', NULL, NULL,
            2, '2026-01-09', ?
        )
        """,
        ("0" * 64,),
    )
    connection.execute(
        """
        INSERT INTO drug_fts(rowid, registered_name, trade_name, insurance_name, manufacturer)
        SELECT rowid, registered_name, trade_name, insurance_name, manufacturer
        FROM drug
        ORDER BY code
        """
    )

    result = connection.execute(
        "SELECT count(*) FROM drug_fts WHERE drug_fts MATCH ?", ("二甲双胍",)
    ).fetchone()

    assert result == (1,)
