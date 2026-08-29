# Data Notice

## 中文声明

本项目不拥有、也不主张拥有所收集的第三方医疗健康数据。根目录的 MIT
License 仅授权项目贡献者自行创作的软件代码和原创项目文档，除非具体文件另有说明。

MIT License 默认不适用于原始来源数据、从第三方数据生成的规范化逐条数据、SQLite、
Parquet、Mapping 数据产物，也不适用于第三方名称、标识或商标。项目不能授予自己并不
拥有的权利。每个 Dataset 必须根据其来源条款和 Rights Gate 单独确定可使用、修改和
再分发的范围。

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

## Current source snapshot

The local `nhsa-drugs` development baseline is distributed through a Jiangxi
medical-security workbook and is recorded as `review-required` in its Dataset
Contract. It may be used for local parser development, but its normalized data,
SQLite database, and Parquet output must not be published until the Rights Gate
records an adequate legal basis and allowed artifact types.

Raw files under `tmp/` are ignored by Git and are never release artifacts.
Source authority, acquisition evidence, retention, and redistribution status
must be reviewed independently for every dataset.

See [`docs/data-rights.md`](docs/data-rights.md) for the project policy.
