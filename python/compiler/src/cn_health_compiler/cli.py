"""Command-line entry point for compiler operations."""

from pathlib import Path
from typing import Annotated

import typer

from cn_health_compiler import __version__
from cn_health_compiler.core.dataset import find_repository_root
from cn_health_compiler.core.validation import validate_dataset_contracts

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


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
