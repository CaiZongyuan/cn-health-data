"""Parse the pinned WS/T 886 Markdown table projection."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

_STANDARD_MARKERS = (
    "WS/T 886—2026",
    "临床检验常用项目名称及代码",
    "2026 - 05 - 25 发布",
    "2026 - 11 - 01 实施",
)
_TEST_HEADERS = ("序号", "代码", "检验项目名称", "类别", "分析物", "标本类型", "标度")
_CATEGORY_HEADERS = ("代码", "临床检验常用项目的类别")
_SPECIMEN_HEADERS = ("代码", "临床检验常用项目的标本类型")
_SCALE_HEADERS = ("代码", "标度")
_CODE = re.compile(r"^[0-9]{7}[A-D]$")
_MATH = {
    "A_2": "A₂",
    r"\alpha_{1}": "α₁",
    r"\beta_{2}": "β₂",
}


class NHCClinicalLabFormatError(ValueError):
    """Raised when the WS/T 886 conversion violates its pinned structure."""


@dataclass(frozen=True, slots=True)
class NHCLaboratoryTestRecord:
    code: str
    name: str
    category_code: str
    category_name: str
    analyte: str
    specimen_code: str
    specimen_name: str
    scale_code: str
    scale_name: str
    source_standard: str
    source_version: str
    source_location: str
    source_row: int
    source_sha256: str


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._math = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "table":
            if self._table is not None:
                raise NHCClinicalLabFormatError("nested HTML table is not supported")
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "eq" and self._cell is not None:
            self._math = True

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            value = _MATH.get(data, data) if self._math else data
            self._cell.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag == "eq":
            self._math = False
        elif tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _tables_by_headers(
    tables: list[list[list[str]]], headers: tuple[str, ...]
) -> list[list[list[str]]]:
    matches = [table for table in tables if table and tuple(table[0]) == headers]
    if not matches:
        raise NHCClinicalLabFormatError(
            f"expected at least one table with headers {headers!r}"
        )
    return matches


def _single_table_by_headers(
    tables: list[list[list[str]]], headers: tuple[str, ...]
) -> list[list[str]]:
    matches = _tables_by_headers(tables, headers)
    if len(matches) != 1:
        raise NHCClinicalLabFormatError(
            f"expected one appendix table with headers {headers!r}, found {len(matches)}"
        )
    return matches[0]


def _dictionary(table: list[list[str]], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for row in table[1:]:
        if len(row) != 2 or not row[0] or not row[1]:
            raise NHCClinicalLabFormatError(f"{label} dictionary has an invalid row")
        if row[0] in result:
            raise NHCClinicalLabFormatError(f"{label} dictionary has duplicate code {row[0]}")
        result[row[0]] = row[1]
    return result


def iter_nhc_laboratory_records(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[NHCLaboratoryTestRecord]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise NHCClinicalLabFormatError("WS/T 886 source is unreadable UTF-8") from error
    missing_markers = [marker for marker in _STANDARD_MARKERS if marker not in text]
    if missing_markers:
        raise NHCClinicalLabFormatError(f"WS/T 886 markers are missing: {missing_markers!r}")

    parser = _TableParser()
    parser.feed(text)
    parser.close()
    test_segments = _tables_by_headers(parser.tables, _TEST_HEADERS)
    tests = [_TEST_HEADERS, *(row for segment in test_segments for row in segment[1:])]
    categories = _dictionary(
        _single_table_by_headers(parser.tables, _CATEGORY_HEADERS), "category"
    )
    specimens = _dictionary(
        _single_table_by_headers(parser.tables, _SPECIMEN_HEADERS), "specimen"
    )
    scales = _dictionary(_single_table_by_headers(parser.tables, _SCALE_HEADERS), "scale")

    for expected_ordinal, row in enumerate(tests[1:], start=1):
        if len(row) != len(_TEST_HEADERS) or any(not value for value in row):
            raise NHCClinicalLabFormatError(f"table 1 row {expected_ordinal} is incomplete")
        ordinal_text, code, name, category_name, analyte, specimen_name, scale_name = row
        if ordinal_text != str(expected_ordinal):
            raise NHCClinicalLabFormatError(
                f"table 1 ordinal changed: expected {expected_ordinal}, found {ordinal_text!r}"
            )
        if _CODE.fullmatch(code) is None:
            raise NHCClinicalLabFormatError(f"table 1 row {expected_ordinal} has invalid code")
        category_code, specimen_code, scale_code = code[:2], code[5:7], code[7]
        if categories.get(category_code) != category_name:
            raise NHCClinicalLabFormatError(
                f"{code} category does not match appendix A.2: {category_name!r}"
            )
        if specimens.get(specimen_code) != specimen_name:
            raise NHCClinicalLabFormatError(
                f"{code} specimen does not match appendix A.3: {specimen_name!r}"
            )
        if scales.get(scale_code) != scale_name:
            raise NHCClinicalLabFormatError(
                f"{code} scale does not match appendix A.4: {scale_name!r}"
            )
        yield NHCLaboratoryTestRecord(
            code=code,
            name=name,
            category_code=category_code,
            category_name=category_name,
            analyte=analyte,
            specimen_code=specimen_code,
            specimen_name=specimen_name,
            scale_code=scale_code,
            scale_name=scale_name,
            source_standard="WS/T 886—2026",
            source_version=source_version,
            source_location=f"表 1/序号 {expected_ordinal}",
            source_row=expected_ordinal,
            source_sha256=source_sha256,
        )
