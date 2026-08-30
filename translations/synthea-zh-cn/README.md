# synthea-zh-cn

This directory owns versioned Simplified Chinese display designations for the
pinned Synthea consumer profile. It does not map source codes to Chinese coding
systems and does not alter clinical values, dates, units, or references.

The pinned catalog contains 2,180 displays: 22 reviewed records are `approved`
(including 18 project-curated LOINC records), and 2,158 API-generated records received an independent agent
review and are marked `machine-checked`. A subsequent evidence review resolved
all 51 flagged records; 18 resolutions identify Synthea module context or code
selection issues while retaining the display of the actual coded concept. See
`review-resolutions.jsonl` and `coverage.json` for the auditable baseline.

Translation generation is a build-time workflow. Normal CI, Bundle projection,
and runtime services do not call a translation API. Strict projection accepts
only `approved` records; the complete machine-checked catalog requires an
explicit experimental option.

`Claim` and `ExplanationOfBenefit` are excluded. Chinese reimbursement and
claims behavior require a separate specification.

The repository MIT License does not relicense third-party terminology
identifiers or source displays in the catalog. Distribution requires a separate
review of the terms applicable to SNOMED CT, LOINC, RxNorm, CVX, DICOM, and the
other recorded systems; `translation.yaml` therefore marks this catalog as not
release-eligible by default.

Apply the display catalog after identity localization:

```bash
uv run cn-health-build synthea translation project \
  --input .work/localized-bundle.json \
  --catalog translations/synthea-zh-cn/catalog.jsonl \
  --output .work/localized-bundle.zh-CN.json \
  --report .work/localized-bundle.zh-CN.report.json \
  --release-id synthea-zh-cn@2026-08-30.r1 \
  --allow-machine-draft
```

The CLI option is named for the least-reviewed stage it can permit; this catalog
currently has no machine-draft records. The runtime service exposes a separate explicit experimental seam. It requires
`CN_HEALTH_SYNTHEA_TRANSLATION_CATALOG_PATH` and
`CN_HEALTH_SYNTHEA_CLINICAL_DISPLAY_PROJECTION_ID`, plus the content-binding
`CN_HEALTH_SYNTHEA_EXPECTED_CATALOG_SHA256`. Startup fails unless the expected
hash exactly matches the loaded catalog's canonical SHA-256. The service accepts `approved`,
`human-reviewed`, and `machine-checked` (never `machine-draft`), and fails the
request closed on any translation gap. It removes `Claim` and
`ExplanationOfBenefit`. The request path loads only the local catalog and has no
external translation API. Provenance labels this boundary
`reviewMode: experimental-preview`; that is not a claim that this catalog is
release-eligible for distribution.
