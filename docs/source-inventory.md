# Source Inventory

| Dataset ID | Source | Format | Version | Acquisition | Terms metadata | Status |
|---|---|---|---|---|---|---|
| `geography-cn` | Pinned AreaCity administrative divisions plus GeoNames China places/postal data | CSV + ZIP/TSV | 2026-08-29 source collection | Manual local and official download | Recorded per component in Dataset Contract and Candidate Manifest | Verified local Candidate |
| `names-cn` | Pinned Faker `zh_CN` person provider | Python source parsed as AST literals | 40.37.0 | Manual local | Upstream commit and source metadata recorded in Dataset Contract | Verified local Candidate |
| `population-cn` | UN World Population Prospects 2024, Medium projection, China rows | gzip CSV | WPP2024 | Official download | Recorded in Dataset Contract and Candidate Manifest | Verified local Candidate |
| `laboratory-cn` | Project-authored curated Chinese laboratory/vital-sign catalog with LOINC/UCUM crosswalks | CSV | 2026-08-30 | Repository source | MIT covers original catalog content; external standards retain their own terms | Verified local Candidate |
| `loinc-zh-cn` | Operator-supplied official LOINC package | ZIP/CSV | From package | Manual local | Recorded from supplied package | Source required |
| `nhc-icd10-clinical` | NHC clinical edition workbook, `2.0（2022版）` | XLSX | 2022 | Manual local | Recorded in Candidate Manifest | Experimental |
| `nhc-procedure-clinical` | NHC clinical edition workbook | XLSX | 2022 | Manual local | Recorded in Dataset Contract | Deferred |
| `nhsa-drugs` | Declared drug classification/code workbook, `总表` | XLSX | 2026-01-09 | Manual local | Recorded in Candidate Manifest | Experimental |

Detailed hashes and fingerprints live in each dataset's `dataset.yaml` and
source-specific configuration.

`laboratory-cn` is a focused project-authored catalog for current consumers. It
does not claim to reproduce the official complete LOINC Chinese linguistic
variant. The separate LOINC adapter is covered by synthetic ZIP/CSV tests, but
no official source package is present in the current local inputs. Supplying a
package determines the exact member layout, version, and source terms recorded
by its `loinc-zh-cn` Candidate.

`nhc-procedure-clinical` remains planned but implementation is explicitly
deferred; its local workbook is not consumed by any build command.
