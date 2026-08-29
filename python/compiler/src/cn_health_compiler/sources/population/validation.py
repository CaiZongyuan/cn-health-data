"""Streaming validation for Chinese aggregate population records."""

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from cn_health_compiler.sources.population.records import PopulationAgeSexRecord


class PopulationValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_age_group_count: int = Field(ge=1)
    min_record_count: int = Field(ge=1)
    min_year_count: int = Field(ge=1)


class PopulationValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    year_count: int
    minimum_year: int
    maximum_year: int
    age_group_count: int


class PopulationRecordValidator:
    def __init__(self, rules: PopulationValidationRules) -> None:
        self._rules = rules
        self._codes: set[str] = set()
        self._year_age_starts: Counter[tuple[int, int]] = Counter()
        self._year_counts: Counter[int] = Counter()
        self._finished = False

    def consume(self, record: PopulationAgeSexRecord) -> None:
        if self._finished:
            raise RuntimeError("cannot consume records after validation is finished")
        if record.code in self._codes:
            raise ValueError(f"duplicate population code: {record.code}")
        if record.country_code != "CHN" or record.variant != "Medium":
            raise ValueError("population record has unexpected scope")
        self._codes.add(record.code)
        self._year_age_starts[(record.year, record.age_start)] += 1
        self._year_counts[record.year] += 1

    def finish(self) -> PopulationValidationReport:
        if self._finished:
            raise RuntimeError("validation is already finished")
        self._finished = True
        if len(self._codes) < self._rules.min_record_count:
            raise ValueError("population record count is below minimum")
        if len(self._year_counts) < self._rules.min_year_count:
            raise ValueError("population year count is below minimum")
        if any(count != 1 for count in self._year_age_starts.values()):
            raise ValueError("population year contains duplicate age groups")
        unexpected_years = {
            year: count
            for year, count in self._year_counts.items()
            if count != self._rules.expected_age_group_count
        }
        if unexpected_years:
            raise ValueError(
                f"population years have unexpected age-group counts: {unexpected_years}"
            )
        years = tuple(self._year_counts)
        return PopulationValidationReport(
            record_count=len(self._codes),
            year_count=len(years),
            minimum_year=min(years),
            maximum_year=max(years),
            age_group_count=self._rules.expected_age_group_count,
        )
