"""Validation rules for the WS/T 886 authority projection."""

from pydantic import BaseModel, ConfigDict, Field

from cn_health_compiler.sources.nhc_lab.records import NHCLaboratoryTestRecord


class NHCLaboratoryValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_record_count: int = Field(ge=1)
    expected_category_count: int = Field(ge=1)
    expected_specimen_count: int = Field(ge=1)
    allowed_scales: dict[str, str] = Field(min_length=1)
    required_codes: list[str] = Field(min_length=1)


class NHCLaboratoryValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    category_count: int
    specimen_count: int
    scale_counts: dict[str, int]
    source_standard: str
    source_version: str


class NHCLaboratoryRecordValidator:
    def __init__(self, rules: NHCLaboratoryValidationRules) -> None:
        self._rules = rules
        self._codes: set[str] = set()
        self._categories: set[tuple[str, str]] = set()
        self._specimens: set[tuple[str, str]] = set()
        self._scale_counts = {code: 0 for code in rules.allowed_scales}
        self._standard: str | None = None
        self._version: str | None = None
        self._finished = False

    def consume(self, record: NHCLaboratoryTestRecord) -> None:
        if self._finished:
            raise RuntimeError("cannot consume records after validation is finished")
        if record.code in self._codes:
            raise ValueError(f"duplicate WS/T 886 code: {record.code}")
        if self._rules.allowed_scales.get(record.scale_code) != record.scale_name:
            raise ValueError(f"invalid WS/T 886 scale: {record.code}")
        if self._standard not in (None, record.source_standard):
            raise ValueError("source standard changed within WS/T 886 records")
        if self._version not in (None, record.source_version):
            raise ValueError("source version changed within WS/T 886 records")
        self._codes.add(record.code)
        self._categories.add((record.category_code, record.category_name))
        self._specimens.add((record.specimen_code, record.specimen_name))
        self._scale_counts[record.scale_code] += 1
        self._standard = record.source_standard
        self._version = record.source_version

    def finish(self) -> NHCLaboratoryValidationReport:
        if self._finished:
            raise RuntimeError("validation is already finished")
        self._finished = True
        if len(self._codes) != self._rules.expected_record_count:
            raise ValueError(
                "WS/T 886 record count changed: "
                f"expected {self._rules.expected_record_count}, found {len(self._codes)}"
            )
        if len(self._categories) != self._rules.expected_category_count:
            raise ValueError("WS/T 886 category count changed")
        if len(self._specimens) != self._rules.expected_specimen_count:
            raise ValueError("WS/T 886 specimen count changed")
        missing = sorted(set(self._rules.required_codes) - self._codes)
        if missing:
            raise ValueError(f"required WS/T 886 codes are missing: {', '.join(missing)}")
        if self._standard is None or self._version is None:
            raise ValueError("WS/T 886 source identity is missing")
        return NHCLaboratoryValidationReport(
            record_count=len(self._codes),
            category_count=len(self._categories),
            specimen_count=len(self._specimens),
            scale_counts=self._scale_counts,
            source_standard=self._standard,
            source_version=self._version,
        )
