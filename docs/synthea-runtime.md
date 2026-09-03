# Synthea Runtime Distribution

The Synthea localization runtime is an experimental-preview consumer projection.
It is published independently from the native `cn-health` CLI and the eight
default Datasets.

## Consumer contract

The current runtime is
`ghcr.io/caizongyuan/cn-health-synthea-localizer:2026-08-29.r4-preview.1`.
Its GitHub Release records the immutable image digest. Consumers that require a
reproducible deployment must use that digest rather than the mutable tag.
[`distribution/synthea-runtime.json`](../distribution/synthea-runtime.json) is
the single owner for the release tag, image coordinates and platforms, profile,
Dataset dependencies, and clinical display catalog. The Release also attaches
that Manifest, a `synthea-cn-profile.tar.gz` archive, and its SHA-256 file for
non-container consumers.

The image contains and verifies:

- `synthea-cn@2026-08-29.r4`;
- `geography-cn@2026-08-29.r2`;
- `names-cn@40.37.0.r2`;
- `population-cn@WPP2024.r2`;
- `synthea-zh-cn@2026-08-30.r1` with its canonical catalog hash.

The configured user is `10001:10001`. The image requires no host data mounts,
writable application directories, source checkout, or runtime network access.
Run it with a read-only filesystem and a writable `/tmp` tmpfs. `/health` and
every successful localization response expose the same profile, dependency,
identity algorithm, and clinical display provenance.

The clinical display catalog remains `experimental-preview`. The image and its
output must not be described as a release-eligible terminology distribution.
`DATA-NOTICE.md` owns attribution and data-rights notices.

## Profile rebuild

Maintainers materialize the three exact signed Dataset Releases before building
a profile. `load_dataset_release_reference` accepts both contributor Candidate
Manifests and verified public materializations whose compressed artifact declares
the materialized `data.sqlite` hash and size.

```bash
cn-health --data-dir .work/cn-health-cache dataset materialize \
  geography-cn geography-cn@2026-08-29.r2 \
  --registry https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/distribution/registry.json \
  --public-key distribution/registry.pub \
  --output .work/synthea-inputs/geography-cn --json
cn-health --data-dir .work/cn-health-cache dataset materialize \
  names-cn names-cn@40.37.0.r2 \
  --registry https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/distribution/registry.json \
  --public-key distribution/registry.pub \
  --output .work/synthea-inputs/names-cn --json
cn-health --data-dir .work/cn-health-cache dataset materialize \
  population-cn population-cn@WPP2024.r2 \
  --registry https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/distribution/registry.json \
  --public-key distribution/registry.pub \
  --output .work/synthea-inputs/population-cn --json
uv run cn-health-build synthea profile \
  --geography-release .work/synthea-inputs/geography-cn \
  --names-release .work/synthea-inputs/names-cn \
  --population-release .work/synthea-inputs/population-cn \
  --output-root .work/synthea-profile \
  --profile-version 2026-08-29 \
  --build-revision 4 \
  --reference-year 2026 \
  --synthea-commit d9d07a6eef91ee5144293b42ab64224d84d124f8
```

The generated profile is promoted to
`distribution/profiles/synthea-cn/<storage-key>/` only after its Manifest and all
declared files pass `test_public_synthea_profile_matches_its_manifest`.

## Image release

`Dockerfile.synthea-localizer` reads the runtime Manifest, builds the Python
runtime, and materializes the three declared compressed public SQLite artifacts
into the image. The tag format is
`synthea-cn-<profile-storage-key>-preview.<revision>`.

Pushing a matching tag runs `.github/workflows/synthea-runtime.yml`. The workflow
builds and exercises the image without host mounts, publishes Linux amd64 and
arm64 manifests to GHCR, attaches SBOM and build provenance, and creates a
GitHub prerelease containing the immutable digest. A release tag must point to a
commit already merged into `main`.
