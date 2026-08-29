"""Streaming validation for canonical NHSA drug records."""

import re
from collections import Counter
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from cn_health_compiler.core.dataset import load_yaml_mapping
from cn_health_compiler.sources.nhsa_drugs.records import (
    DRUG_RECORD_FIELD_NAMES,
    DrugRecord,
)


class DrugValidationError(ValueError):
    """Raised when canonical drug data fails a release-blocking rule."""


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


class AllowedValueRules(_RulesModel):
    market_status: tuple[str, ...]


class DrugValidationRules(_RulesModel):
    source: SourceRules
    record_count: RecordCountRules
    required: tuple[str, ...]
    max_null_rate: dict[str, float]
    unique: tuple[str, ...]
    code: CodeRules
    allowed_values: AllowedValueRules

    @classmethod
    def load_dataset(cls, path: Path) -> Self:
        contract = load_yaml_mapping(path)
        return cls.model_validate(contract["validation"])

    @model_validator(mode="after")
    def rules_reference_canonical_fields(self) -> Self:
        referenced_fields = set(self.required) | set(self.max_null_rate) | set(self.unique)
        unknown_fields = referenced_fields - DRUG_RECORD_FIELD_NAMES
        if unknown_fields:
            raise ValueError(f"validation rules reference unknown fields: {sorted(unknown_fields)}")
        if self.unique != ("code",):
            raise ValueError("the NHSA drug adapter requires code as its unique key")
        invalid_rates = {
            field_name: rate
            for field_name, rate in self.max_null_rate.items()
            if not 0 <= rate <= 1
        }
        if invalid_rates:
            raise ValueError(f"null-rate thresholds must be between zero and one: {invalid_rates}")
        return self


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    unique_codes: int
    null_counts: tuple[tuple[str, int], ...]
    market_status_counts: tuple[tuple[str, int], ...]


class DrugRecordValidator:
    """Validate records incrementally and retain only aggregate state and keys."""

    def __init__(self, rules: DrugValidationRules) -> None:
        self._rules = rules
        self._code_pattern = re.compile(rules.code.pattern)
        self._seen_codes: set[str] = set()
        self._null_counts: Counter[str] = Counter()
        self._market_status_counts: Counter[str] = Counter()
        self._record_count = 0
        self._finished = False

    def consume(self, record: DrugRecord) -> None:
        if self._finished:
            raise RuntimeError("cannot consume records after validation is finished")
        if record.source_sha256 != self._rules.source.sha256:
            raise DrugValidationError("record source SHA256 does not match validation rules")
        if (
            self._code_pattern.fullmatch(record.code) is None
            or len(record.code) not in self._rules.code.allowed_lengths
        ):
            raise DrugValidationError(
                f"invalid code {record.code!r} at source row {record.source_row}"
            )
        if record.code in self._seen_codes:
            raise DrugValidationError(
                f"duplicate code {record.code} at source row {record.source_row}"
            )
        if record.market_status not in self._rules.allowed_values.market_status:
            raise DrugValidationError(
                f"invalid market_status {record.market_status!r} at source row {record.source_row}"
            )
        for field_name in self._rules.required:
            if getattr(record, field_name) is None:
                raise DrugValidationError(
                    f"required field {field_name} is null at source row {record.source_row}"
                )

        self._seen_codes.add(record.code)
        self._record_count += 1
        self._market_status_counts[record.market_status] += 1
        for field_name in DRUG_RECORD_FIELD_NAMES:
            if getattr(record, field_name) is None:
                self._null_counts[field_name] += 1

    def finish(self) -> ValidationReport:
        if self._finished:
            raise RuntimeError("validation is already finished")
        self._finished = True
        if self._record_count != self._rules.record_count.baseline:
            raise DrugValidationError(
                "record count changed: "
                f"expected {self._rules.record_count.baseline}, found {self._record_count}"
            )
        if self._record_count < self._rules.record_count.min:
            raise DrugValidationError(
                f"record count {self._record_count} is below {self._rules.record_count.min}"
            )
        for field_name, max_rate in self._rules.max_null_rate.items():
            null_count = self._null_counts[field_name]
            null_rate = null_count / self._record_count
            if null_rate > max_rate:
                raise DrugValidationError(
                    f"null rate for {field_name} is {null_rate:.6f}; maximum is {max_rate:.6f}"
                )

        return ValidationReport(
            record_count=self._record_count,
            unique_codes=len(self._seen_codes),
            null_counts=tuple(sorted(self._null_counts.items())),
            market_status_counts=tuple(sorted(self._market_status_counts.items())),
        )
