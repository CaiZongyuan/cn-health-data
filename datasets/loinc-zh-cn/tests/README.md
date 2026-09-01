# LOINC fixtures

Project-generated split and combined ZIP/CSV fixtures exercise the complete
Candidate path:

- bounded ZIP inspection, member hashes/sizes, exact ordered headers, and UTF-8 BOMs;
- complete core-table import and nullable Simplified Chinese joins;
- UCUM grammar validation, SYSTEM part links, and panel/member closure;
- Dataset Schema v2, SQLite/FTS/bigram, per-table Parquet, Diff, and Manifest;
- reproducible SQLite/canonical hashes and atomic failure behavior;
- the `cn-health-build build loinc-zh-cn --translation-source ...` entry point.

The committed fixtures contain only project-generated records. The same pipeline
has been verified locally against the pinned official LOINC 2.83 Complete archive;
the source ZIP and generated Candidate remain Git-ignored.
