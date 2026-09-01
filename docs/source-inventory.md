# Source Inventory

| Dataset ID | Source | Format | Version | Acquisition | Terms metadata | Status |
|---|---|---|---|---|---|---|
| `geography-cn` | Pinned AreaCity administrative divisions plus GeoNames China places/postal data | CSV + ZIP/TSV | 2026-08-29 source collection | Manual local and official download | Recorded per component in Dataset Contract and Candidate Manifest | Public normalized Release |
| `names-cn` | Pinned Faker `zh_CN` person provider | Python source parsed as AST literals | 40.37.0 | Manual local | Upstream commit and source metadata recorded in Dataset Contract | Public normalized Release |
| `population-cn` | UN World Population Prospects 2024, Medium projection, China rows | gzip CSV | WPP2024 | Official download | Recorded in Dataset Contract and Candidate Manifest | Public normalized Release |
| `nhc-lab-tests` | WS/T 886—2026 clinical laboratory names and codes | Markdown conversion of the published standard | 2026 | Explicit manual local input | Standard number, publication/effective dates, hash, size, and normalized-only decision recorded | Public normalized Release |
| `laboratory-cn` | WS/T 886 terminology plus project adult references/simulation metadata; price-project workbook as panel evidence | Markdown + repository CSV + XLSX evidence | 2026-09-01 | Explicit local and repository inputs | All four source identities and the non-crosswalk evidence boundary are recorded in the Candidate Manifest | Public normalized Release |
| `loinc-zh-cn` | Official LOINC Complete archive with `zhCN5` linguistic variant | ZIP/CSV | 2.83 | Authenticated manual local download | LOINC License 5.8, attribution, member hashes, and third-party notices recorded | Public normalized Release |
| `nhc-icd10-clinical` | NHC clinical edition workbook, `2.0（2022版）` | XLSX | 2022 | Manual local | Recorded in Candidate Manifest | Public normalized Release |
| `nhc-procedure-clinical` | NHC clinical edition workbook | XLSX | 2022 | Manual local | Recorded in Dataset Contract | Deferred |
| `nhsa-drugs` | Declared drug classification/code workbook, `总表` | XLSX | 2026-01-09 | Manual local | Recorded in Candidate Manifest | Public normalized Release |

Detailed hashes and fingerprints live in each dataset's `dataset.yaml` and
source-specific configuration.

`nhc-lab-tests` contains all 399 WS/T 886 rows and validates category, specimen,
and scale segments against appendix A. `laboratory-cn` selects 84 of those tests
for adult healthy simulation, with 96 reference records and 15 project-authored
panels. The evidence workbook maps reimbursement projects to 2023 technical
specifications; it is not represented as an official WS/T 886 or LOINC
crosswalk. The separate LOINC compiler is covered by complete synthetic Candidate
tests and a real `loinc-zh-cn@2.83.r2` build. The pinned official Complete archive
contains 112,405 core concepts and 96,518 Chinese translations. Source layout,
hashes, counts, LOINC License 5.8, attribution, and third-party copyright boundary
are recorded in the Dataset Contract, source review, public Manifest, and
bundled license files. The normalized Release is available through the signed
public Registry; the authenticated source archive remains private.

`nhc-procedure-clinical` remains planned but implementation is explicitly
deferred; its local workbook is not consumed by any build command.
