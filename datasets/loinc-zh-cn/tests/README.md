# LOINC fixtures

Project-generated split and combined ZIP/CSV fixtures exercise the complete
Candidate path:

- bounded ZIP inspection, member hashes/sizes, exact ordered headers, and UTF-8 BOMs;
- complete core-table import and nullable Simplified Chinese joins;
- UCUM grammar validation, SYSTEM part links, and panel/member closure;
- Dataset Schema v2, SQLite/FTS/bigram, per-table Parquet, Diff, and Manifest;
- reproducible SQLite/canonical hashes and atomic failure behavior;
- the `cn-health-build build loinc-zh-cn --translation-source ...` entry point.

The committed fixtures contain only project-generated records. A real Candidate
remains blocked until the official source packages, exact layout/version/counts,
and applicable rights are supplied and reviewed.
