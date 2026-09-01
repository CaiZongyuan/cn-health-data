# nhc-lab-tests

`nhc-lab-tests` is the authority projection of WS/T 886—2026, *Names and codes
of common clinical laboratory tests*. It contains the complete 399-row table and
validates each code against the category, specimen, and scale dictionaries in
appendix A.

The local build input is the pinned Markdown conversion named in
`dataset.yaml`. The conversion does not preserve original PDF page boundaries,
so record provenance uses `表 1/序号 N`; no page number is invented. Public
Releases contain normalized SQLite and Parquet artifacts only, never the source
Markdown or the externally referenced image.

This Dataset represents terminology facts only. Units, adult reference ranges,
healthy-result simulation metadata, optional LOINC crosswalks, and hospital
orderable panels belong to `laboratory-cn`.

Build the pinned source explicitly:

```bash
uv run cn-health-build build nhc-lab-tests \
  --source 'tmp/WST_886—2026.md'
```
