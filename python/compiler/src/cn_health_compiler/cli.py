"""Command-line entry point for compiler operations."""

from pathlib import Path
from typing import Annotated

import typer

from cn_health_compiler import __version__
from cn_health_compiler.core.dataset import find_repository_root
from cn_health_compiler.core.registry import build_signed_registry, generate_signing_keypair
from cn_health_compiler.core.validation import validate_dataset_contracts
from cn_health_compiler.sources.nhc_icd10.build import build_diagnosis_candidate
from cn_health_compiler.sources.nhsa_drugs.build import build_nhsa_drug_candidate

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
registry_app = typer.Typer(no_args_is_help=True)
app.add_typer(registry_app, name="registry")


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
    builders = {
        "nhsa-drugs": build_nhsa_drug_candidate,
        "nhc-icd10-clinical": build_diagnosis_candidate,
    }
    builder = builders.get(dataset_id)
    if builder is None:
        raise typer.BadParameter(
            f"build is not implemented for {dataset_id}", param_hint="dataset_id"
        )
    root = repo_root or find_repository_root()
    result = builder(
        repo_root=root,
        source_path=source,
        output_root=output_root or root / "dist",
        build_revision=build_revision,
        sequence=sequence,
        base_release_dir=base_release,
    )
    typer.echo(result.release_dir)
    typer.echo(result.manifest_path)


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
