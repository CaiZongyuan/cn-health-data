# laboratory-cn

`laboratory-cn` schema v2 is the simulation-ready runtime projection for
Chinese HIS, Synthea, and ClinMesh consumers. Its primary clinical identity is
the WS/T 886—2026 code. Optional LOINC identifiers are crosswalks, never primary
keys.

The four runtime tables separate atomic tests, adult references, project-authored
panels, and stable panel membership. Adult applicability is intentionally limited
to `all`, `male`, and `female`. Quantities expose explicit healthy simulation
bounds and precision; qualitative and ordinal tests expose a fixed normal value.
Reference provenance distinguishes national-standard values from clearly marked
project-curated simulation baselines.

`runtime.csv` and `panels.csv` are reviewable project inputs. The terminology
fields are hydrated and checked against the explicitly supplied WS/T 886 source
during every build. The price-project mapping workbook is pinned and validated
as panel evidence, but its reimbursement and 2023 method codes are not presented
as official WS/T 886 or LOINC mappings.

```bash
uv run cn-health-build build laboratory-cn \
  --source 'tmp/WST_886—2026.md' \
  --panel-source 'tmp/检验类医疗服务价格项目立项指南映射关系表.xlsx'
```

The immutable schema v1 Release `laboratory-cn@2026-08-30.r2` remains in the
public distribution. The native runtime detects v1/v2 schemas and continues to
read both.
