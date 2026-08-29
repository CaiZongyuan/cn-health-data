from cn_health_compiler.sources.nhsa_drugs.records import (
    DrugRecord,
    RawDrugRow,
    normalize_raw_drug_row,
)
from cn_health_compiler.sources.nhsa_drugs.validation import DrugValidationRules

SOURCE_SHA256 = "a" * 64
SOURCE_VERSION = "2026-01-09"


def source_values(
    *,
    code: str = "XA01",
    registered_name: str = "测试药品",
    insurance_name: str = "测试药品",
) -> list[str | None]:
    return [
        code,
        "第一批",
        registered_name,
        "无",
        "片剂",
        "片剂",
        "0.5g",
        "0.5g",
        "铝塑",
        "10",
        "片",
        "盒",
        "测试药品企业",
        None,
        "测试生产企业",
        "国药准字TEST",
        None,
        "86900000000000",
        None,
        "上市",
        insurance_name,
        "乙",
        "口服常释剂型",
        "1",
        None,
        "OLD01",
    ]


def raw_drug_row(*, source_row: int = 2, code: str = "XA01") -> RawDrugRow:
    return RawDrugRow.from_values(source_row, source_values(code=code))


def drug_record(
    code: str,
    source_row: int,
    registered_name: str = "盐酸二甲双胍片",
) -> DrugRecord:
    return normalize_raw_drug_row(
        RawDrugRow.from_values(
            source_row,
            source_values(
                code=code,
                registered_name=registered_name,
                insurance_name="二甲双胍",
            ),
        ),
        source_version=SOURCE_VERSION,
        source_sha256=SOURCE_SHA256,
    )


def validation_rules(*, baseline: int = 2) -> DrugValidationRules:
    return DrugValidationRules.model_validate(
        {
            "source": {
                "sha256": SOURCE_SHA256,
                "worksheet": "总表",
                "header_columns": 26,
                "formula_cells": 0,
            },
            "record_count": {
                "baseline": baseline,
                "min": 1,
                "max_relative_decrease": 0.05,
                "max_relative_increase": 0.10,
            },
            "required": ["code", "registered_name", "data_source", "market_status"],
            "max_null_rate": {
                "code": 0,
                "registered_name": 0,
                "data_source": 0,
                "market_status": 0,
            },
            "unique": ["code"],
            "code": {"pattern": "^[A-Z0-9]+$", "allowed_lengths": [4]},
            "allowed_values": {"market_status": ["上市", "停产", "未上市"]},
        }
    )
