"""Streaming validation for Chinese name components."""

from pydantic import BaseModel, ConfigDict, Field

from cn_health_compiler.sources.names.records import NameComponentRecord


class NamesValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_surname_count: int = Field(ge=1)
    min_male_given_count: int = Field(ge=1)
    min_female_given_count: int = Field(ge=1)


class NamesValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    surname_count: int
    male_given_count: int
    female_given_count: int
    deduplicated_surname_count: int


class NamesRecordValidator:
    def __init__(self, rules: NamesValidationRules) -> None:
        self._rules = rules
        self._codes: set[str] = set()
        self._surname_count = 0
        self._male_given_count = 0
        self._female_given_count = 0
        self._deduplicated_surname_count = 0
        self._finished = False

    def consume(self, record: NameComponentRecord) -> None:
        if self._finished:
            raise RuntimeError("cannot consume records after validation is finished")
        if record.code in self._codes:
            raise ValueError(f"duplicate name component code: {record.code}")
        self._codes.add(record.code)
        if record.kind == "surname":
            self._surname_count += 1
            self._deduplicated_surname_count += record.source_duplicate
        elif record.gender == "male":
            self._male_given_count += 1
        else:
            self._female_given_count += 1

    def finish(self) -> NamesValidationReport:
        if self._finished:
            raise RuntimeError("validation is already finished")
        self._finished = True
        counts = (
            ("surname", self._surname_count, self._rules.min_surname_count),
            ("male given name", self._male_given_count, self._rules.min_male_given_count),
            ("female given name", self._female_given_count, self._rules.min_female_given_count),
        )
        for label, count, minimum in counts:
            if count < minimum:
                raise ValueError(f"{label} count {count} is below minimum {minimum}")
        return NamesValidationReport(
            record_count=len(self._codes),
            surname_count=self._surname_count,
            male_given_count=self._male_given_count,
            female_given_count=self._female_given_count,
            deduplicated_surname_count=self._deduplicated_surname_count,
        )
