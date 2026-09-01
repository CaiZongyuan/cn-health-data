"""Command-line entry point for compiler operations."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any, cast

import typer

from cn_health_compiler import __version__
from cn_health_compiler.core.dataset import find_repository_root
from cn_health_compiler.core.manifest import write_json_atomic
from cn_health_compiler.core.registry import build_signed_registry, generate_signing_keypair
from cn_health_compiler.core.validation import validate_dataset_contracts
from cn_health_compiler.sources.geography.build import build_geography_candidate
from cn_health_compiler.sources.laboratory.build import build_laboratory_candidate
from cn_health_compiler.sources.loinc.build import build_loinc_candidate
from cn_health_compiler.sources.names.build import build_names_candidate
from cn_health_compiler.sources.nhc_icd10.build import build_diagnosis_candidate
from cn_health_compiler.sources.nhsa_drugs.build import build_nhsa_drug_candidate
from cn_health_compiler.sources.population.build import build_population_candidate
from cn_health_compiler.synthetic.synthea_localizer import localize_synthea_bundle
from cn_health_compiler.synthetic.synthea_profile import build_synthea_profile
from cn_health_compiler.synthetic.translation.batches import TranslationBatch
from cn_health_compiler.synthetic.translation.catalog import (
    CatalogDisplayLookup,
    ReviewStatus,
    load_catalog,
)
from cn_health_compiler.synthetic.translation.inventory import build_translation_inventory
from cn_health_compiler.synthetic.translation.projector import project_bundle
from cn_health_compiler.synthetic.translation.validation import validate_projection
from cn_health_compiler.synthetic.translation.workflow import (
    batches_from_inventory,
    merge_draft_responses,
    write_catalog_jsonl,
)

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
registry_app = typer.Typer(no_args_is_help=True)
synthea_app = typer.Typer(no_args_is_help=True)
synthea_translation_app = typer.Typer(no_args_is_help=True)
app.add_typer(registry_app, name="registry")
app.add_typer(synthea_app, name="synthea")
synthea_app.add_typer(synthea_translation_app, name="translation")


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
    translation_source: Annotated[
        Path | None,
        typer.Option(
            "--translation-source", exists=True, dir_okay=False, readable=True, resolve_path=True
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
        if translation_source is not None:
            raise typer.BadParameter(
                "--translation-source is only valid for loinc-zh-cn",
                param_hint="dataset_id",
            )
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
    if dataset_id == "loinc-zh-cn":
        if division_source is not None or postal_source is not None:
            raise typer.BadParameter(
                "geography sources are not valid for loinc-zh-cn",
                param_hint="dataset_id",
            )
        result = build_loinc_candidate(
            repo_root=root,
            core_source_path=source,
            translation_source_path=translation_source,
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
    if translation_source is not None:
        raise typer.BadParameter(
            "--translation-source is only valid for loinc-zh-cn",
            param_hint="dataset_id",
        )
    builders = {
        "laboratory-cn": build_laboratory_candidate,
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


@synthea_translation_app.command("inventory")
def synthea_translation_inventory(
    module_dir: Annotated[
        Path,
        typer.Option(
            "--module-dir", exists=True, file_okay=False, readable=True, resolve_path=True
        ),
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False, resolve_path=True)],
    bundle: Annotated[
        list[Path] | None,
        typer.Option("--bundle", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ] = None,
) -> None:
    """Inventory translatable displays in pinned Synthea modules and FHIR Bundles."""
    if output.exists():
        raise typer.BadParameter(
            "refusing to overwrite translation inventory", param_hint="--output"
        )
    inventory = build_translation_inventory(module_dir=module_dir, fhir_bundle_paths=bundle or ())
    write_json_atomic(output, inventory.as_dict())
    typer.echo(output)
    typer.echo(
        f"modules={inventory.module_count} records={len(inventory.records)} "
        f"conflicts={len(inventory.conflicts)} hash={inventory.content_hash}"
    )


@synthea_translation_app.command("make-batches")
def synthea_translation_make_batches(
    module_dir: Annotated[
        Path,
        typer.Option(
            "--module-dir", exists=True, file_okay=False, readable=True, resolve_path=True
        ),
    ],
    output_dir: Annotated[Path, typer.Option("--output-dir", file_okay=False, resolve_path=True)],
    prompt_version: Annotated[str, typer.Option("--prompt-version")],
    bundle: Annotated[
        list[Path] | None,
        typer.Option("--bundle", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ] = None,
    max_records: Annotated[int, typer.Option("--max-records", min=1, max=100)] = 30,
    max_source_characters: Annotated[int, typer.Option("--max-source-characters", min=1)] = 6_000,
) -> None:
    """Create deterministic, bounded translation request batches."""
    if output_dir.exists() and any(output_dir.iterdir()):
        raise typer.BadParameter(
            "translation batch directory is not empty", param_hint="--output-dir"
        )
    inventory = build_translation_inventory(module_dir=module_dir, fhir_bundle_paths=bundle or ())
    batches = batches_from_inventory(
        inventory,
        prompt_version=prompt_version,
        max_records=max_records,
        max_source_characters=max_source_characters,
    )
    write_json_atomic(output_dir / "inventory.json", inventory.as_dict())
    pending_dir = output_dir / "batches" / "pending"
    for batch_value in batches:
        write_json_atomic(
            pending_dir / f"{batch_value.batch_id}.json",
            batch_value.model_dump(by_alias=True),
        )
    write_json_atomic(
        output_dir / "batch-index.json",
        {
            "schemaVersion": 1,
            "inventoryHash": inventory.content_hash,
            "recordCount": len(inventory.records),
            "batchCount": len(batches),
            "batches": [
                {
                    "batchId": value.batch_id,
                    "recordCount": len(value.records),
                    "path": f"batches/pending/{value.batch_id}.json",
                }
                for value in batches
            ],
        },
    )
    typer.echo(output_dir / "batch-index.json")
    typer.echo(f"records={len(inventory.records)} batches={len(batches)}")


@synthea_translation_app.command("merge-drafts")
def synthea_translation_merge_drafts(
    batches_dir: Annotated[
        Path,
        typer.Option(
            "--batches-dir", exists=True, file_okay=False, readable=True, resolve_path=True
        ),
    ],
    responses_dir: Annotated[
        Path,
        typer.Option(
            "--responses-dir", exists=True, file_okay=False, readable=True, resolve_path=True
        ),
    ],
    inventory_path: Annotated[
        Path,
        typer.Option("--inventory", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    output: Annotated[Path, typer.Option("--output", dir_okay=False, resolve_path=True)],
    model_id: Annotated[str, typer.Option("--model-id")],
) -> None:
    """Validate exact batch responses and merge them into a machine-draft catalog."""
    if output.exists():
        raise typer.BadParameter("refusing to overwrite translation catalog", param_hint="--output")
    batch_values = tuple(
        TranslationBatch.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(batches_dir.glob("*.json"))
    )
    raw_responses: dict[str, dict[str, object]] = {}
    for path in sorted(responses_dir.glob("*.json")):
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("batchId"), str):
            raise typer.BadParameter(
                f"invalid draft response: {path}", param_hint="--responses-dir"
            )
        raw_responses[str(raw["batchId"])] = cast(dict[str, object], raw)
    inventory_raw: object = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(inventory_raw, dict) or not isinstance(inventory_raw.get("conflicts"), list):
        raise typer.BadParameter("invalid translation inventory", param_hint="--inventory")
    conflicts: set[tuple[str, str | None, str]] = set()
    for value in inventory_raw["conflicts"]:
        if not isinstance(value, dict):
            raise typer.BadParameter("invalid inventory conflict", param_hint="--inventory")
        system, version, code = (
            value.get("sourceSystem"),
            value.get("sourceVersion"),
            value.get("sourceCode"),
        )
        if not isinstance(system, str) or not isinstance(code, str):
            raise typer.BadParameter("invalid inventory conflict key", param_hint="--inventory")
        conflicts.add((system, version if isinstance(version, str) else None, code))
    catalog = merge_draft_responses(
        batch_values,
        raw_responses,
        model_id=model_id,
        conflicts=frozenset(conflicts),
    )
    catalog_hash, _ = write_catalog_jsonl(output, catalog)
    typer.echo(output)
    typer.echo(f"records={len(catalog.records)} hash={catalog_hash}")


@synthea_translation_app.command("project")
def synthea_translation_project(
    input_path: Annotated[
        Path,
        typer.Option("--input", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    catalog_path: Annotated[
        Path,
        typer.Option("--catalog", exists=True, dir_okay=False, readable=True, resolve_path=True),
    ],
    output_path: Annotated[Path, typer.Option("--output", dir_okay=False, resolve_path=True)],
    report_path: Annotated[Path, typer.Option("--report", dir_okay=False, resolve_path=True)],
    release_id: Annotated[str, typer.Option("--release-id")],
    allow_machine_draft: Annotated[bool, typer.Option("--allow-machine-draft")] = False,
) -> None:
    """Apply a reviewed or explicit experimental display catalog to one Bundle."""
    if output_path.exists() or report_path.exists():
        raise typer.BadParameter("refusing to overwrite translation output")
    raw: object = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise typer.BadParameter("input Bundle must be a JSON object", param_hint="--input")
    source_bundle = cast(dict[str, Any], raw)
    catalog = load_catalog(catalog_path)
    accepted: frozenset[ReviewStatus] = (
        frozenset({"approved", "human-reviewed", "machine-checked", "machine-draft"})
        if allow_machine_draft
        else frozenset({"approved"})
    )
    lookup = CatalogDisplayLookup(catalog, accepted_review_statuses=accepted)
    projected = project_bundle(
        source_bundle,
        lookup,
        release_id=release_id,
        content_hash=catalog.sha256,
    )
    validation = validate_projection(source_bundle, projected.bundle, review_lookup=lookup)
    write_json_atomic(output_path, projected.bundle)
    write_json_atomic(report_path, asdict(validation))
    typer.echo(output_path)
    typer.echo(
        f"translated={validation.translated} gaps={validation.gap} "
        f"removed={len(validation.removed_resources)}"
    )


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
