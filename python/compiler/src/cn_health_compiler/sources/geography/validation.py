"""Validation rules for Chinese geography records."""

from pydantic import BaseModel, ConfigDict, Field

from cn_health_compiler.sources.geography.records import (
    AdministrativeDivisionRecord,
    GeographyPlaceRecord,
    GeographyPostalAreaRecord,
)


class GeographyValidationRules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_division_count: int = Field(default=0, ge=0)
    min_place_count: int = Field(ge=0)
    min_postal_count: int = Field(ge=0)


class GeographyValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_count: int
    place_count: int
    postal_count: int
    administrative_division_count: int
    geonames_administrative_count: int
    populated_place_count: int


def validate_geography_records(
    divisions: list[AdministrativeDivisionRecord],
    places: list[GeographyPlaceRecord],
    postal_areas: list[GeographyPostalAreaRecord],
    rules: GeographyValidationRules,
) -> GeographyValidationReport:
    division_codes = {record.code for record in divisions}
    division_external_codes = {record.external_code for record in divisions}
    place_codes = {record.code for record in places}
    postal_codes = {record.code for record in postal_areas}
    if len(division_codes) != len(divisions):
        raise ValueError("administrative division codes are not unique")
    if len(division_external_codes) != len(divisions):
        raise ValueError("administrative division external codes are not unique")
    if any(
        record.parent_code is not None and record.parent_code not in division_codes
        for record in divisions
    ):
        raise ValueError("administrative division parent code is missing")
    if len(place_codes) != len(places):
        raise ValueError("geography place codes are not unique")
    if len(postal_codes) != len(postal_areas):
        raise ValueError("geography postal area codes are not unique")
    if len(divisions) < rules.min_division_count:
        raise ValueError(
            f"administrative division count is below minimum {rules.min_division_count}"
        )
    if len(places) < rules.min_place_count:
        raise ValueError(f"geography place count is below minimum {rules.min_place_count}")
    if len(postal_areas) < rules.min_postal_count:
        raise ValueError(f"geography postal count is below minimum {rules.min_postal_count}")
    geonames_administrative_count = sum(
        record.kind == "administrative-division" for record in places
    )
    populated_count = len(places) - geonames_administrative_count
    return GeographyValidationReport(
        record_count=len(divisions) + len(places) + len(postal_areas),
        place_count=len(places),
        postal_count=len(postal_areas),
        administrative_division_count=len(divisions),
        geonames_administrative_count=geonames_administrative_count,
        populated_place_count=populated_count,
    )
