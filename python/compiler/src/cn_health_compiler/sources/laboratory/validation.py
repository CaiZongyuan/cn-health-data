"""Validation for the curated Chinese laboratory catalog."""

from pydantic import BaseModel, ConfigDict, Field

from cn_health_compiler.sources.laboratory.records import LaboratoryConceptRecord


class LaboratoryValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed_ucum_units: list[str] = Field(min_length=1)
    expected_record_count: int = Field(ge=1)
    required_codes: list[str] = Field(min_length=1)
    terminology_version: str = Field(min_length=1)


class LaboratoryValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    chemistry_count: int
    hematology_count: int
    vital_sign_count: int
    terminology_version: str


class LaboratoryRecordValidator:
    def __init__(self, rules: LaboratoryValidationRules) -> None:
        self._rules = rules
        self._codes: set[str] = set()
        self._category_counts = {"chemistry": 0, "hematology": 0, "vital-sign": 0}
        self._finished = False

    def consume(self, record: LaboratoryConceptRecord) -> None:
        if self._finished:
            raise RuntimeError("cannot consume records after validation is finished")
        if record.code in self._codes:
            raise ValueError(f"duplicate laboratory concept code: {record.code}")
        if record.terminology_version != self._rules.terminology_version:
            raise ValueError(f"laboratory terminology version mismatch: {record.code}")
        if record.ucum_unit is not None and record.ucum_unit not in self._rules.allowed_ucum_units:
            raise ValueError(f"laboratory UCUM unit is not allowed: {record.code}")
        self._codes.add(record.code)
        self._category_counts[record.category] += 1

    def finish(self) -> LaboratoryValidationReport:
        if self._finished:
            raise RuntimeError("validation is already finished")
        self._finished = True
        if len(self._codes) != self._rules.expected_record_count:
            raise ValueError(
                "laboratory record count changed: "
                f"expected {self._rules.expected_record_count}, found {len(self._codes)}"
            )
        missing = sorted(set(self._rules.required_codes) - self._codes)
        if missing:
            raise ValueError(f"required laboratory concepts are missing: {', '.join(missing)}")
        return LaboratoryValidationReport(
            record_count=len(self._codes),
            chemistry_count=self._category_counts["chemistry"],
            hematology_count=self._category_counts["hematology"],
            vital_sign_count=self._category_counts["vital-sign"],
            terminology_version=self._rules.terminology_version,
        )
