"""Parse literal Chinese name components from the Faker zh_CN provider."""

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast


class FakerNamesFormatError(ValueError):
    """Raised when the pinned Faker provider no longer matches the adapter contract."""


@dataclass(frozen=True, slots=True)
class NameComponentRecord:
    code: str
    kind: Literal["surname", "given-name"]
    gender: Literal["any", "female", "male"]
    text: str
    weight: float
    is_compound: bool
    source_duplicate: bool
    source_line: int
    source_ordinal: int
    source_version: str
    source_sha256: str


def _provider_class(module: ast.Module) -> ast.ClassDef:
    providers = [
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "Provider"
    ]
    if len(providers) != 1:
        raise FakerNamesFormatError("Faker source must contain exactly one Provider class")
    return providers[0]


def _assignments(provider: ast.ClassDef) -> dict[str, ast.Assign]:
    assignments: dict[str, ast.Assign] = {}
    for node in provider.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            assignments[node.targets[0].id] = node
    return assignments


def _name_list(assignment: ast.Assign | None, label: str) -> list[tuple[str, int]]:
    if assignment is None or not isinstance(assignment.value, (ast.List, ast.Tuple)):
        raise FakerNamesFormatError(f"{label} must be a literal name list")
    names: list[tuple[str, int]] = []
    for value in assignment.value.elts:
        if (
            not isinstance(value, ast.Constant)
            or not isinstance(value.value, str)
            or not value.value
        ):
            raise FakerNamesFormatError(f"{label} must contain non-empty string literals")
        names.append((value.value, value.lineno))
    if len({name for name, _ in names}) != len(names):
        raise FakerNamesFormatError(f"{label} contains duplicate names")
    return names


def _surnames(assignment: ast.Assign | None) -> list[tuple[str, float, int, bool]]:
    if assignment is None or not isinstance(assignment.value, ast.Call):
        raise FakerNamesFormatError("last_names must be a literal OrderedDict")
    call = assignment.value
    if (
        not isinstance(call.func, ast.Name)
        or call.func.id != "OrderedDict"
        or len(call.args) != 1
        or call.keywords
    ):
        raise FakerNamesFormatError("last_names must be a literal OrderedDict")
    try:
        pairs = ast.literal_eval(call.args[0])
    except (ValueError, TypeError) as error:
        raise FakerNamesFormatError("last_names must be a literal OrderedDict") from error
    if not isinstance(pairs, (list, tuple)):
        raise FakerNamesFormatError("last_names must contain literal pairs")
    surname_values: dict[str, tuple[float, int]] = {}
    duplicate_names: set[str] = set()
    for ordinal, pair in enumerate(pairs):
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not pair[0]
            or not isinstance(pair[1], (int, float))
            or isinstance(pair[1], bool)
            or pair[1] <= 0
        ):
            raise FakerNamesFormatError("last_names contains an invalid weighted pair")
        name = pair[0]
        if name in surname_values:
            duplicate_names.add(name)
        surname_values[name] = (float(pair[1]), call.args[0].lineno + ordinal)
    return [
        (name, weight, source_line, name in duplicate_names)
        for name, (weight, source_line) in surname_values.items()
    ]


def parse_faker_name_components(
    path: Path,
    *,
    source_version: str,
    source_sha256: str,
) -> Iterator[NameComponentRecord]:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        raise FakerNamesFormatError("Faker source is not valid Python syntax") from error
    assignments = _assignments(_provider_class(module))
    surnames = _surnames(assignments.get("last_names"))
    male_names = _name_list(assignments.get("first_names_male"), "first_names_male")
    female_names = _name_list(assignments.get("first_names_female"), "first_names_female")

    ordinal = 0
    for name, weight, source_line, source_duplicate in surnames:
        ordinal += 1
        yield NameComponentRecord(
            code=f"surname:{name}",
            kind="surname",
            gender="any",
            text=name,
            weight=weight,
            is_compound=len(name) > 1,
            source_duplicate=source_duplicate,
            source_line=source_line,
            source_ordinal=ordinal,
            source_version=source_version,
            source_sha256=source_sha256,
        )
    for gender, names in cast(
        tuple[tuple[Literal["female", "male"], list[tuple[str, int]]], ...],
        (("male", male_names), ("female", female_names)),
    ):
        for name, source_line in names:
            ordinal += 1
            yield NameComponentRecord(
                code=f"given-name:{gender}:{name}",
                kind="given-name",
                gender=gender,
                text=name,
                weight=1.0,
                is_compound=False,
                source_duplicate=False,
                source_line=source_line,
                source_ordinal=ordinal,
                source_version=source_version,
                source_sha256=source_sha256,
            )
