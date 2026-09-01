# Source Inventory

| Dataset ID | Source | Format | Version | Acquisition | Terms metadata | Status |
|---|---|---|---|---|---|---|
| `geography-cn` | Pinned AreaCity administrative divisions plus GeoNames China places/postal data | CSV + ZIP/TSV | 2026-08-29 source collection | Manual local and official download | Recorded per component in Dataset Contract and Candidate Manifest | Public normalized Release |
| `names-cn` | Pinned Faker `zh_CN` person provider | Python source parsed as AST literals | 40.37.0 | Manual local | Upstream commit and source metadata recorded in Dataset Contract | Public normalized Release |
| `population-cn` | UN World Population Prospects 2024, Medium projection, China rows | gzip CSV | WPP2024 | Official download | Recorded in Dataset Contract and Candidate Manifest | Public normalized Release |
| `laboratory-cn` | Project-authored curated Chinese laboratory/vital-sign catalog with LOINC/UCUM crosswalks | CSV | 2026-08-30 | Repository source | MIT covers original catalog content; external standards retain their own terms | Public normalized Release |
| `loinc-zh-cn` | Official LOINC Complete archive with `zhCN5` linguistic variant | ZIP/CSV | 2.83 | Authenticated manual local download | LOINC License 5.8, attribution, member hashes, and third-party notices recorded | Public normalized Release |
| `nhc-icd10-clinical` | NHC clinical edition workbook, `2.0（2022版）` | XLSX | 2022 | Manual local | Recorded in Candidate Manifest | Public normalized Release |
| `nhc-procedure-clinical` | NHC clinical edition workbook | XLSX | 2022 | Manual local | Recorded in Dataset Contract | Deferred |
| `nhsa-drugs` | Declared drug classification/code workbook, `总表` | XLSX | 2026-01-09 | Manual local | Recorded in Candidate Manifest | Public normalized Release |

Detailed hashes and fingerprints live in each dataset's `dataset.yaml` and
source-specific configuration.

`laboratory-cn` is a focused project-authored catalog for current consumers. It
does not claim to reproduce the official complete LOINC Chinese linguistic
variant. The separate LOINC compiler is covered by complete synthetic Candidate
tests and a real `loinc-zh-cn@2.83.r2` build. The pinned official Complete archive
contains 112,405 core concepts and 96,518 Chinese translations. Source layout,
hashes, counts, LOINC License 5.8, attribution, and third-party copyright boundary
are recorded in the Dataset Contract, source review, public Manifest, and
bundled license files. The normalized Release is available through the signed
public Registry; the authenticated source archive remains private.

`nhc-procedure-clinical` remains planned but implementation is explicitly
deferred; its local workbook is not consumed by any build command.
