"""Streaming validation for NHC clinical diagnosis records."""

import re
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.sources.nhc_icd10.records import DiagnosisRecord


class DiagnosisValidationError(ValueError):
    """Raised when diagnosis data fails a release-blocking rule."""


class _RulesModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRules(_RulesModel):
    sha256: str
    worksheet: str
    header_columns: int
    formula_cells: int


class RecordCountRules(_RulesModel):
    baseline: int
    min: int
    max_relative_decrease: float
    max_relative_increase: float


class CodeRules(_RulesModel):
    pattern: str
    allowed_lengths: tuple[int, ...]


class DiagnosisValidationRules(_RulesModel):
    source: SourceRules
    record_count: RecordCountRules
    required: tuple[str, ...]
    max_null_rate: dict[str, float]
    unique: tuple[str, ...]
    code: CodeRules

    @classmethod
    def load_dataset(cls, path: Path) -> Self:
        contract = load_yaml_mapping(path)
        return cls.model_validate(contract["validation"])


class DiagnosisValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    unique_codes: int
    main_code_count: int
    additional_only_count: int
    paired_code_count: int


class DiagnosisRecordValidator:
    def __init__(self, rules: DiagnosisValidationRules) -> None:
        self._rules = rules
        self._pattern = re.compile(rules.code.pattern)
        self._seen: set[str] = set()
        self._count = 0
        self._main_count = 0
        self._additional_only_count = 0
        self._paired_count = 0
        self._finished = False

    def consume(self, record: DiagnosisRecord) -> None:
        if self._finished:
            raise RuntimeError("cannot consume records after validation is finished")
        if record.source_sha256 != self._rules.source.sha256:
            raise DiagnosisValidationError("record source SHA256 does not match validation rules")
        if (
            self._pattern.fullmatch(record.code) is None
            or len(record.code) not in self._rules.code.allowed_lengths
        ):
            raise DiagnosisValidationError(
                f"invalid code {record.code!r} at source row {record.source_row}"
            )
        if record.code in self._seen:
            raise DiagnosisValidationError(
                f"duplicate code {record.code} at source row {record.source_row}"
            )
        self._seen.add(record.code)
        self._count += 1
        if record.main_code is not None:
            self._main_count += 1
        else:
            self._additional_only_count += 1
        if record.main_code is not None and record.additional_code is not None:
            self._paired_count += 1

    def finish(self) -> DiagnosisValidationReport:
        if self._finished:
            raise RuntimeError("validation is already finished")
        self._finished = True
        if self._count != self._rules.record_count.baseline:
            raise DiagnosisValidationError(
                f"record count changed: expected {self._rules.record_count.baseline}, "
                f"found {self._count}"
            )
        return DiagnosisValidationReport(
            record_count=self._count,
            unique_codes=len(self._seen),
            main_code_count=self._main_count,
            additional_only_count=self._additional_only_count,
            paired_code_count=self._paired_count,
        )
