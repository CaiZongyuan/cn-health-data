"""Command-line entry point for compiler operations."""

import json
from pathlib import Path
from typing import Annotated

import typer

from cn_health_compiler import __version__
from cn_health_compiler.core.dataset import find_repository_root
from cn_health_compiler.core.manifest import write_json_atomic
from cn_health_compiler.core.registry import build_signed_registry, generate_signing_keypair
from cn_health_compiler.core.validation import validate_dataset_contracts
from cn_health_compiler.sources.geography.build import build_geography_candidate
from cn_health_compiler.sources.names.build import build_names_candidate
from cn_health_compiler.sources.nhc_icd10.build import build_diagnosis_candidate
from cn_health_compiler.sources.nhsa_drugs.build import build_nhsa_drug_candidate
from cn_health_compiler.sources.population.build import build_population_candidate
from cn_health_compiler.synthetic.synthea_localizer import localize_synthea_bundle
from cn_health_compiler.synthetic.synthea_profile import build_synthea_profile

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
registry_app = typer.Typer(no_args_is_help=True)
synthea_app = typer.Typer(no_args_is_help=True)
app.add_typer(registry_app, name="registry")
app.add_typer(synthea_app, name="synthea")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """Compile and validate CN Health reference datasets."""


@app.command("validate-contracts")
def validate_contracts(
    repo_root: Annotated[
        Path | None,
        typer.Option("--repo-root", file_okay=False, resolve_path=True),
    ] = None,
) -> None:
    """Validate every datasets/*/dataset.yaml against the contract schema."""
    root = repo_root or find_repository_root()
    validated = validate_dataset_contracts(root)
    for contract_path in validated:
        typer.echo(contract_path.relative_to(root))
    typer.echo(f"validated {len(validated)} dataset contracts")


@app.command("build")
def build_dataset(
    dataset_id: str,
    source: Annotated[
        Path,
        typer.Option("--source", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    division_source: Annotated[
        Path | None,
        typer.Option(
            "--division-source", exists=True, dir_okay=False, readable=True, resolve_path=True
        ),
    ] = None,
    postal_source: Annotated[
        Path | None,
        typer.Option(
            "--postal-source", exists=True, dir_okay=False, readable=True, resolve_path=True
        ),
    ] = None,
    repo_root: Annotated[
        Path | None,
        typer.Option("--repo-root", file_okay=False, resolve_path=True),
    ] = None,
    output_root: Annotated[
        Path | None,
        typer.Option("--output-root", file_okay=False, resolve_path=True),
    ] = None,
    base_release: Annotated[
        Path | None,
        typer.Option("--base-release", file_okay=False, exists=True, resolve_path=True),
    ] = None,
    build_revision: Annotated[int, typer.Option("--build-revision", min=1)] = 1,
    sequence: Annotated[int, typer.Option("--sequence", min=1)] = 1,
) -> None:
    """Build an immutable local Dataset Candidate."""
    root = repo_root or find_repository_root()
    target_output_root = output_root or root / "dist"
    if dataset_id == "geography-cn":
        if division_source is None or postal_source is None:
            raise typer.BadParameter(
                "geography-cn requires --division-source and --postal-source",
                param_hint="dataset_id",
            )
        result = build_geography_candidate(
            repo_root=root,
            gazetteer_path=source,
            division_path=division_source,
            postal_path=postal_source,
            output_root=target_output_root,
            build_revision=build_revision,
            sequence=sequence,
            base_release_dir=base_release,
        )
        typer.echo(result.release_dir)
        typer.echo(result.manifest_path)
        return
    if division_source is not None or postal_source is not None:
        raise typer.BadParameter(
            "additional geography sources are only valid for geography-cn",
            param_hint="dataset_id",
        )
    builders = {
        "names-cn": build_names_candidate,
        "nhsa-drugs": build_nhsa_drug_candidate,
        "nhc-icd10-clinical": build_diagnosis_candidate,
        "population-cn": build_population_candidate,
    }
    builder = builders.get(dataset_id)
    if builder is None:
        raise typer.BadParameter(
            f"build is not implemented for {dataset_id}", param_hint="dataset_id"
        )
    result = builder(
        repo_root=root,
        source_path=source,
        output_root=target_output_root,
        build_revision=build_revision,
        sequence=sequence,
        base_release_dir=base_release,
    )
    typer.echo(result.release_dir)
    typer.echo(result.manifest_path)


@synthea_app.command("profile")
def build_synthea_cn_profile(
    names_release: Annotated[
        Path,
        typer.Option("--names-release", exists=True, file_okay=False, resolve_path=True),
    ],
    geography_release: Annotated[
        Path,
        typer.Option("--geography-release", exists=True, file_okay=False, resolve_path=True),
    ],
    population_release: Annotated[
        Path,
        typer.Option("--population-release", exists=True, file_okay=False, resolve_path=True),
    ],
    output_root: Annotated[
        Path,
        typer.Option("--output-root", file_okay=False, resolve_path=True),
    ],
    profile_version: Annotated[str, typer.Option("--profile-version")],
    reference_year: Annotated[int, typer.Option("--reference-year", min=1900, max=2200)],
    synthea_commit: Annotated[str, typer.Option("--synthea-commit")],
    repo_root: Annotated[
        Path | None,
        typer.Option("--repo-root", file_okay=False, resolve_path=True),
    ] = None,
    build_revision: Annotated[int, typer.Option("--build-revision", min=1)] = 1,
) -> None:
    """Build a versioned Chinese Synthea resource profile."""
    result = build_synthea_profile(
        repo_root=repo_root or find_repository_root(),
        names_release_dir=names_release,
        geography_release_dir=geography_release,
        population_release_dir=population_release,
        output_root=output_root,
        profile_version=profile_version,
        reference_year=reference_year,
        synthea_commit=synthea_commit,
        build_revision=build_revision,
    )
    typer.echo(result.profile_dir)
    typer.echo(result.manifest_path)


@synthea_app.command("localize")
def localize_synthea_r4_bundle(
    input_path: Annotated[
        Path,
        typer.Option("--input", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    output_path: Annotated[
        Path,
        typer.Option("--output", dir_okay=False, resolve_path=True),
    ],
    profile: Annotated[
        Path,
        typer.Option("--profile", exists=True, file_okay=False, resolve_path=True),
    ],
    names_release: Annotated[
        Path,
        typer.Option("--names-release", exists=True, file_okay=False, resolve_path=True),
    ],
    geography_release: Annotated[
        Path,
        typer.Option("--geography-release", exists=True, file_okay=False, resolve_path=True),
    ],
    population_release: Annotated[
        Path,
        typer.Option("--population-release", exists=True, file_okay=False, resolve_path=True),
    ],
    seed: Annotated[str, typer.Option("--seed")],
) -> None:
    """Localize one Synthea FHIR R4 collection Bundle for China."""
    if output_path.exists():
        raise typer.BadParameter("refusing to overwrite localized Bundle", param_hint="--output")
    raw: object = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise typer.BadParameter("input Bundle must be a JSON object", param_hint="--input")
    localized = localize_synthea_bundle(
        raw,
        profile_dir=profile,
        names_release_dir=names_release,
        geography_release_dir=geography_release,
        population_release_dir=population_release,
        seed=seed,
    )
    sha256, _ = write_json_atomic(output_path, localized.bundle)
    typer.echo(output_path)
    typer.echo(sha256)


@registry_app.command("keygen")
def registry_keygen(
    private_key: Annotated[Path, typer.Option("--private-key")],
    public_key: Annotated[Path, typer.Option("--public-key")],
) -> None:
    """Generate a raw Ed25519 Registry signing keypair."""
    key_id = generate_signing_keypair(private_key, public_key)
    typer.echo(key_id)


@registry_app.command("build")
def registry_build(
    manifests: Annotated[list[Path], typer.Argument(exists=True, dir_okay=False)],
    manifest_base_url: Annotated[str, typer.Option("--manifest-base-url")],
    private_key: Annotated[Path, typer.Option("--private-key", exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output")] = Path("registry.json"),
    signature: Annotated[Path, typer.Option("--signature")] = Path("registry.json.sig"),
    repo_root: Annotated[
        Path | None,
        typer.Option("--repo-root", file_okay=False, resolve_path=True),
    ] = None,
) -> None:
    """Build and sign a release-eligible public Registry."""
    root = repo_root or find_repository_root()
    build_signed_registry(
        manifests,
        registry_path=output,
        signature_path=signature,
        private_key_path=private_key,
        schema_path=root / "schemas" / "registry.schema.json",
        manifest_base_url=manifest_base_url,
    )
    typer.echo(output)
    typer.echo(signature)
