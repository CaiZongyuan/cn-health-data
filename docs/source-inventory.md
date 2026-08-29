# Source Inventory

| Dataset ID | Source | Format | Version | Acquisition | Terms metadata | Status |
|---|---|---|---|---|---|---|
| `loinc-zh-cn` | Operator-supplied official LOINC package | ZIP/CSV | From package | Manual local | Recorded from supplied package | Source required |
| `nhc-icd10-clinical` | NHC clinical edition workbook, `2.0（2022版）` | XLSX | 2022 | Manual local | Recorded in Candidate Manifest | Experimental |
| `nhc-procedure-clinical` | NHC clinical edition workbook | XLSX | 2022 | Manual local | Recorded in Dataset Contract | Deferred |
| `nhsa-drugs` | Declared drug classification/code workbook, `总表` | XLSX | 2026-01-09 | Manual local | Recorded in Candidate Manifest | Experimental |

Detailed hashes and fingerprints live in each dataset's `dataset.yaml` and
source-specific configuration.

The LOINC adapter is covered by synthetic ZIP/CSV tests, but no official source
package is present in the current local inputs. Supplying a package determines
the exact member layout, version, and source terms recorded by its Candidate.

`nhc-procedure-clinical` remains planned but implementation is explicitly
deferred; its local workbook is not consumed by any build command.
