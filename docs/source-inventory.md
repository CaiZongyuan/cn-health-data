# Source Inventory

| Dataset ID | Source | Format | Version | Acquisition | Rights | Status |
|---|---|---|---|---|---|---|
| `loinc-zh-cn` | To be confirmed | ZIP/CSV | To be confirmed | To be confirmed | Review required | Planned |
| `nhc-icd10-clinical` | NHC clinical edition workbook, `2.0（2022版）` | XLSX | 2022 | Manual local | Review required | Experimental |
| `nhc-procedure-clinical` | NHC clinical edition workbook | XLSX | 2022 | Manual local | Review required | Planned |
| `nhsa-drugs` | Jiangxi distribution workbook, `总表` | XLSX | 2026-01-09 | Manual local | Review required | Experimental |

Detailed hashes and fingerprints live in each dataset's `dataset.yaml` and
source-specific configuration.

The LOINC adapter is covered by synthetic ZIP/CSV tests, but no real source
package is present. Source acquisition, exact member layout, version, and
redistribution rights must be confirmed before changing its status or building
a Candidate.
