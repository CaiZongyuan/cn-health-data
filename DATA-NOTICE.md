# Data Notice

## 中文声明

本项目不拥有、也不主张拥有所收集的第三方医疗健康数据。根目录的 MIT
License 仅授权项目贡献者自行创作的软件代码和原创项目文档，除非具体文件另有说明。

MIT License 默认不适用于原始来源数据、从第三方数据生成的规范化逐条数据、SQLite、
Parquet、Mapping 数据产物，也不适用于第三方名称、标识或商标。项目不能授予自己并不
拥有的权利。每个 Dataset 的 Contract 与 Manifest 单独记录来源条款、署名和可用的
产物类型，数据使用方据此判断适用于自身用途的范围。

## License scope

The root [MIT License](LICENSE) applies to repository-owned software code and
original project documentation unless a file states otherwise. The project
does not own or claim ownership of third-party healthcare source data.

The MIT License does not, by itself, grant permission to use or redistribute:

- raw or mirrored third-party source data;
- normalized record-level data derived from third-party sources;
- generated SQLite, Parquet, mapping, or similar data artifacts; or
- third-party names, logos, marks, and other protected material.

Each Dataset Contract and Release Manifest must state its independent rights
status, legal basis, attribution, and allowed artifact types. Where those
records conflict with the software license, the more specific data-rights
record controls the data artifact.

This notice does not make a legal determination about whether an individual
fact is copyrightable. It prevents the project from purporting to grant rights
that it does not hold.

## Current source snapshots

The current drug and diagnosis baselines are built from explicitly supplied local
workbooks. Their Candidate Manifests preserve the authority role, acquisition
method, source fingerprint, source version, and distribution metadata. These
record-level Candidates are local build outputs and are not bundled with the
repository's MIT-licensed software.

Raw files under `tmp/` are ignored by Git and are never release artifacts.
Source authority, acquisition evidence, retention, and distribution metadata are
recorded independently for every dataset.

The signed public starter Registry is a narrow exception to the default local
Candidate policy. It contains only the project-authored `laboratory-cn` catalog
whose Manifest records `redistribution: public` and `releaseEligible: true`.
LOINC and UCUM identifiers continue to identify their respective external
standards; the starter is not the complete official LOINC Chinese package.

See [`docs/data-rights.md`](docs/data-rights.md) for the project policy.
