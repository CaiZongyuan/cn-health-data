# CN Health Data 实施手册

> 中国医疗健康 Reference Data 的采集、标准化、版本化、发布与本地查询基础设施

**建议统一 CLI：** `cn-health`

**建议 Python Compiler 包：** `cn-health-compiler`

---

## 0. 文档说明

本文档是 `cn-health-data` 项目的长期工程实施手册，用于统一项目的目标、边界、架构、目录规范、Dataset Contract、数据编译流程、质量控制、版本管理、本地运行时、CLI、发布方式以及后续扩展策略。

本文档的目标不是描述某个特定 HIS、Synthea 扩展或 Agent 产品，而是定义一套可以被不同医疗软件复用的中国医疗 Reference Data 基础设施。

典型消费者包括但不限于：

- 医疗信息系统和 HIS 仿真环境；
- Synthea 等合成患者生成器；
- 医疗 Agent 与 Agent Harness；
- FHIR Server 和 terminology service；
- LIS、药房、医保和医院目录模拟系统；
- 医疗科研、数据分析和教学系统；
- 医疗软件开发、测试和 Benchmark 环境。

项目应尽量保持**消费者无关**。

### 0.1 当前实施基线

截至本手册当前版本，`nhsa-drugs` 的首个可实现基线已经确定：

- 输入文件：通过 `--source` 显式提供、且匹配 Dataset Contract 指纹的药品分类与代码工作簿；
- Dataset Source Version：`2026-01-09`，取自文件名声明的数据截至日期；
- Canonical 输入工作表：`总表`；
- `西药中成药新增变更` 和 `本省双通道` 仅作为来源文件中的辅助工作表，不参与首版 canonical 合并；
- 首版不解析 `tmp/医保药品分类与代码数据(西药、中成药)截至2026年8月14日.pdf`，也不从官网 PDF 发现、下载或同步药品数据；
- `tmp/` 是 gitignore 的本地输入收件箱，不是可发布目录，也不是稳定的构建缓存。

以后若切换药品来源，必须作为显式 Dataset Contract 变更处理，重新确认字段映射、权利状态、版本衔接和 Validation 基线；不得在后台静默混合 XLSX 与 PDF。

---

# 1. 项目背景

中国医疗健康领域拥有大量权威的国家级和地方级数据资源，例如：

- 疾病分类与代码；
- 手术操作分类；
- 医保药品分类与代码；
- 药品注册信息；
- 国家医保药品目录；
- 医疗服务价格项目；
- 医用耗材；
- 体外诊断试剂；
- 医疗机构诊疗科目；
- DRG / DIP；
- 医疗器械 UDI；
- LOINC 中文数据；
- 行政区划和人口统计资料。

问题在于，这些数据长期分散于：

```text
政府网站
PDF
XLSX
ZIP
CSV
查询系统
公告附件
动态数据库
标准文件
```

不同来源的：

- 数据格式不同；
- 更新频率不同；
- 字段定义不同；
- 版本体系不同；
- 数据质量不同；
- 发布方式不同；
- 开发者获取方式不同。

开发一个中国医疗系统时，开发者往往不得不重复完成：

```text
找数据
↓
下载
↓
理解字段
↓
解析 PDF / Excel
↓
清洗
↓
建立数据库
↓
写查询代码
↓
处理版本
↓
重新维护
```

这导致大量重复工程。

`cn-health-data` 希望填补的就是这一层。

---

# 2. 项目定位

一句话定义：

> **CN Health Data 是面向中国医疗健康软件、科研与 Agent 系统的开源、机器可读、版本化、可追溯 Reference Data 基础设施。**

项目不是单纯的数据爬虫，也不是一个政府网站镜像。

完整的数据价值链是：

```text
Official Source
      ↓
Source Adapter
      ↓
Extraction
      ↓
Normalization
      ↓
Validation
      ↓
Versioning
      ↓
Canonical Dataset
      ↓
SQLite / Parquet
      ↓
CLI / SDK / Application
```

真正需要长期维护的资产包括：

1. 数据源发现能力；
2. Parser；
3. Canonical Schema；
4. 数据映射；
5. 数据质量规则；
6. 版本历史；
7. Provenance；
8. Runtime；
9. Developer Experience。

---

# 3. 核心目标

## 3.1 第一目标：机器可读

将原本存在于：

```text
PDF
Excel
ZIP
CSV
Web Query
```

中的 Reference Data 转换为稳定的数据模型，例如：

```text
SQLite
Parquet
JSON metadata
```

让开发者不再直接处理政府网站和 PDF。

---

## 3.2 第二目标：版本化

医疗 Reference Data 不是静态数据。

例如药品数据库可能频繁更新。

项目需要表达：

```text
2026-01-09
2026-02-06
2026-03-06
...
```

而不是只维护：

```text
latest.json
```

历史版本必须是 immutable artifact。

---

## 3.3 第三目标：可追溯

任意一条 Dataset Release 都应该能够回答：

```text
来自哪个机构？
原始来源是什么？
官方发布日期是什么？
数据截至什么时间？
原文件 SHA256 是什么？
使用哪个 Parser 构建？
构建出了多少条记录？
经过什么转换？
质量检查是否通过？
```

---

## 3.4 第四目标：快速本地查询

Reference Data 天然适合本地运行。

最终目标：

```bash
cn-health drug search "二甲双胍"

cn-health diagnosis search "糖尿病"

cn-health loinc search "糖化血红蛋白"
```

不要求用户：

- 部署数据库服务器；
- 注册 API；
- 配置 API Key；
- 使用 PostgreSQL；
- 联网调用远程服务。

核心模式：

```text
download once
     ↓
local SQLite
     ↓
millisecond lookup
```

---

## 3.5 第五目标：Agent-native

CLI 是项目的一等接口。

Agent 通常已经拥有：

```text
shell
exec
filesystem
```

因此：

```bash
cn-health drug search "阿莫西林" --json
```

比强制接入 MCP、HTTP API 或 SDK 更通用。

对于 Agent 来说，`cn-health` 应像：

```text
git
rg
jq
gh
sqlite3
```

一样自然。

---

# 4. 明确的非目标

项目早期不做以下事情。

## 4.1 不做生产级医疗系统

项目提供 Reference Data，不承担：

- 医疗诊断；
- 临床决策；
- 真实医保结算；
- 真实患者数据管理；
- 医疗机构生产运行。

---

## 4.2 不保存真实患者数据

项目不得把：

```text
真实患者姓名
身份证
电话
病历
检验结果
诊疗记录
```

作为 Reference Dataset。

人口数据仅使用：

- 聚合统计；
- 分布模型；
- 合成数据。

---

## 4.3 不做真实医院运行数据库镜像

国家药品全集和一家医院药房库存不是一个概念。

本项目负责：

```text
中国有哪些药品
```

消费者负责：

```text
这家医院采购了哪些药
库存多少
多少钱
在哪个药房
```

---

## 4.4 第一阶段不做云数据库产品

暂不优先实现：

```text
Cloudflare D1
Cloudflare Worker API
PostgreSQL Service
Elasticsearch
Managed Terminology Server
```

先证明：

```text
Source → SQLite → CLI
```

这一闭环。

---

# 5. 数据世界的四层模型

这是项目最重要的领域边界之一。

```text
L0 National Reference Data
           │
           ▼
L1 Regional Policy / Reference
           │
           ▼
L2 Hospital Baseline
           │
           ▼
L3 Runtime Facts
```

---

## 5.1 L0：National Reference Data

回答：

> 中国医疗体系中“有什么”。

例如：

```text
疾病
药品
手术操作
医疗服务项目
耗材
LOINC
诊疗科目
医保目录
UDI
```

这是 `cn-health-data` 的核心范围。

---

## 5.2 L1：Regional Data

回答：

> 某省、市如何执行相关政策。

例如：

```text
浙江省医疗服务价格
某地区医保支付政策
地方医保支付标准
地方限定支付范围
```

这一层可以逐步进入 `cn-health-data`。

目录建议：

```text
regions/
└── zhejiang/
```

---

## 5.3 L2：Hospital Baseline

回答：

> 某一家医院具体有哪些目录和资源。

例如：

```text
医院药品目录
医院诊断字典
医院 LIS 项目
本地项目代码
药房
科室
医生
价格
库存初始值
```

原则上不属于 `cn-health-data`。

它应该由消费者根据 Reference Data 生成。

---

## 5.4 L3：Runtime Facts

回答：

> 医院今天真正发生了什么。

例如：

```text
Patient
Encounter
Order
Result
Prescription
Charge
Payment
Dispense
Inventory Movement
```

完全不属于本项目。

---

# 6. 初始 Dataset 范围

## P0：核心 Reference Data

第一阶段优先：

```text
loinc-zh-cn
nhc-icd10-clinical
nhc-procedure-clinical
nhsa-drugs
nmpa-drugs
nhsa-medical-services
nhc-departments
population-cn
geography-cn
```

其中第一批真正实施：

```text
01 loinc-zh-cn
02 nhc-icd10-clinical
03 nhc-procedure-clinical
04 nhsa-drugs
```

---

## P1：扩展医疗数据

后续：

```text
nrdl
nhsa-consumables
nmpa-udi
nhsa-ivd
drg
dip
regional-medical-service-prices
```

---

# 7. 总体技术架构

```text
                         BUILD TIME

 Declared Sources
 Local Snapshot / Official XLSX / CSV / ZIP / Web / PDF
             │
             ▼
      Source Resolution
             │
             ▼
      Acquire / Snapshot
             │
             ▼
         Inspection
             │
             ▼
          Extraction
             │
             ▼
       Raw/Staging Data
             │
             ▼
       Normalization
             │
             ▼
        Validation
             │
             ▼
      Version Comparison
             │
             ▼
      Canonical Dataset
             │
       ┌─────┴─────┐
       ▼           ▼
    SQLite       Parquet
       │
       ▼
   compression
       │
       ▼
 Dataset Release


                        RUNTIME

 Dataset Release
       │
       ▼
 cn-health install
       │
       ▼
 Local SQLite
       │
       ▼
 Rust Runtime
       │
 ┌─────┼─────────┐
 ▼     ▼         ▼
CLI   Agent   Application
```

---

# 8. 技术栈

## 8.1 Python

用途：

```text
Source Resolution
Acquire / Snapshot
PDF Extraction
Excel Parsing
Normalization
Validation
Build
```

环境管理：

```text
uv
```

原因：

- Python 数据处理生态成熟；
- PDF 工具成熟；
- Excel 工具成熟；
- 快速迭代；
- 非常适合 ETL。

可能使用：

```text
PyMuPDF
pdfplumber
openpyxl
Polars
DuckDB
Pydantic
Typer
httpx
```

不要求所有库一开始都引入。

---

# 9. DuckDB 的定位

DuckDB 不是 Runtime Database。

其角色是：

> **Build-time analytical database。**

典型使用场景：

```text
多数据源 JOIN
大量行处理
版本 Diff
去重
复杂 Validation
统计分析
Parquet 操作
```

例如：

```sql
SELECT *
FROM new_drugs n
LEFT JOIN old_drugs o USING(code)
WHERE o.code IS NULL;
```

获得新增记录。

---

## 9.1 什么时候不需要 DuckDB

例如一个：

```text
37,000 rows XLSX
```

完全可以：

```text
openpyxl
  ↓
Python normalization
  ↓
SQLite
```

无需为了架构漂亮而引入 DuckDB。

原则：

> **复杂度出现以后再引入 DuckDB，而不是所有数据都强制经过 DuckDB。**

---

# 10. SQLite 的定位

SQLite 是：

> **Canonical Runtime Artifact。**

不是 staging database。

适合：

```text
exact lookup
local search
FTS
CLI
embedded application
offline use
```

最终用户下载的是已经：

```text
建表
建索引
建立 FTS
ANALYZE
VACUUM
```

完成的数据库。

用户不需要再 import CSV。

---

# 11. Rust 的定位

Rust 第一阶段只负责：

> **Runtime / CLI。**

不负责：

```text
PDF Parsing
Excel ETL
Source Compiler
```

核心功能：

```text
dataset install
dataset update
SQLite lookup
FTS search
JSON output
local cache
zstd decompression
manifest parsing
```

主要库可考虑：

```text
clap
rusqlite
reqwest
serde
serde_json
zstd
directories
```

---

# 12. npm / pnpm 的定位

JavaScript 不是 Runtime Core。

npm package 主要负责：

> **提供极低门槛的 `npx cn-health` 使用体验。**

开发依赖统一使用：

```text
pnpm
```

推荐整体工具链：

```text
Python       uv
Node/npm     pnpm
Rust         Cargo
```

---

# 13. 推荐仓库结构

```text
cn-health-data/
│
├── README.md
├── LICENSE
├── DATA-NOTICE.md
├── CONTRIBUTING.md
│
├── pyproject.toml
├── uv.lock
├── .python-version
│
├── package.json
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
│
├── Cargo.toml
│
├── datasets/
│   ├── loinc-zh-cn/
│   │   ├── dataset.yaml
│   │   ├── schema.sql
│   │   └── tests/
│   │
│   ├── nhc-icd10-clinical/
│   │   ├── dataset.yaml
│   │   ├── schema.sql
│   │   └── tests/
│   │
│   ├── nhc-procedure-clinical/
│   │   ├── dataset.yaml
│   │   ├── schema.sql
│   │   └── tests/
│   │
│   └── nhsa-drugs/
│       ├── dataset.yaml
│       ├── schema.sql
│       ├── workbook.yaml
│       └── tests/
│
├── python/
│   └── compiler/
│       ├── pyproject.toml
│       └── src/
│           └── cn_health_compiler/
│               ├── cli.py
│               │
│               ├── core/
│               │   ├── dataset.py
│               │   ├── pipeline.py
│               │   ├── manifest.py
│               │   ├── validation.py
│               │   ├── sqlite.py
│               │   └── diff.py
│               │
│               └── sources/
│                   ├── loinc/
│                   ├── nhc_icd10/
│                   ├── nhc_procedure/
│                   └── nhsa_drugs/
│
├── rust/
│   └── cn-health/
│       ├── Cargo.toml
│       └── src/
│
├── npm/
│   └── cn-health/
│       ├── package.json
│       └── bin/
│
├── schemas/
│   ├── manifest.schema.json
│   ├── registry.schema.json
│   ├── dataset.schema.json
│   ├── mapping.schema.json
│   └── cli-output.schema.json
│
├── mappings/
│   ├── snomed-to-icd-cn/
│   ├── rxnorm-to-drug-cn/
│   └── nmpa-to-nhsa/
│
├── docs/
│   ├── architecture.md
│   ├── source-inventory.md
│   ├── dataset-format.md
│   ├── terminology-model.md
│   ├── data-rights.md
│   └── implementation-handbook.md
│
├── scripts/
│
├── .github/
│   └── workflows/
│
├── tmp/
├── .cache/
├── .work/
└── dist/
```

---

# 14. 目录职责原则

## `datasets/`

描述：

> Dataset 是什么。

例如：

```text
dataset.yaml
schema.sql
workbook.yaml / layout.yaml（按来源类型选择）
validation rules
fixtures
```

这里尽量不要堆数据处理实现。

---

## `python/compiler/`

回答：

> Dataset 如何被构建。

实现：

```text
resolve source
snapshot
inspect
extract
normalize
validate
build
diff
```

---

## `rust/`

回答：

> Dataset 如何被最终用户消费。

---

## `npm/`

回答：

> 如何让 Node/npm 用户非常容易获得 Rust CLI。

---

# 15. 工作目录规范

## `tmp/`

人工下载的本地 Source Inbox。

当前 `nhsa-drugs` 的 XLSX 从这里显式传入 Compiler。`tmp/` 必须 gitignore；Compiler 不应按文件名自动挑选“最新”文件，也不应修改其中的文件。进入构建后，输入由 SHA256 标识，后续步骤只读取该不可变快照。

`tmp/` 中同时存在的 PDF、旧版 XLSX 或其他资料不会自动参与构建。

---

## `.work/`

构建临时文件。

```text
.work/
├── sources/
├── extracted/
├── staging/
└── logs/
```

包括原始：

```text
PDF
XLSX
ZIP
CSV
```

全部 gitignore。`extracted/`、`staging/` 和 `logs/` 默认可以在构建后删除；`sources/` 是否保留由 Source Retention Policy 决定。若删除后又无法从不可变来源重新取得，Manifest 必须将 `reproducibleFromSource` 标为 false。

---

## `.cache/`

缓存：

```text
HTTP cache
download cache
tool cache
```

不属于正式数据产品。

---

## `dist/`

构建结果。

例如：

```text
dist/
└── nhsa-drugs/
    └── releases/
        └── 2026-01-09.r1/
            ├── data.sqlite
            ├── data.sqlite.zst
            ├── data.parquet
            ├── manifest.json
            ├── validation.json
            └── diff.json
```

`dist/` 默认不提交 Git。

Release 时上传 GitHub Release 等分发平台。

---

# 16. Dataset Contract

每一个 Dataset 都必须拥有唯一稳定 ID。

例如：

```text
loinc-zh-cn
nhc-icd10-clinical
nhc-procedure-clinical
nhsa-drugs
```

ID 一旦公开使用，不轻易修改。

---

# 17. `dataset.yaml`

用于描述 Dataset 本身。

示例：

```yaml
id: nhsa-drugs

title: 医保药品分类与代码数据库

description: >
  国家医疗保障体系中的药品分类与代码 Reference Dataset。

authority:
  name: 江西省医疗保障局
  role: distribution-source
  verification: pending-source-page

source:
  type: xlsx
  acquisition: manual-local
  path_hint: tmp/江西省医保药品分类与代码数据库更新表(数据更新至2026年1月9日).xlsx
  worksheet: 总表
  declared_data_as_of: "2026-01-09"
  sha256: 9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67
  size_bytes: 39514965
  upstream_sync: false

versioning:
  strategy: declared-data-as-of

output:
  primary: sqlite
  optional:
    - parquet

runtime:
  searchable: true

rights:
  redistribution: review-required
  release_eligible: false
```

`authority.role: distribution-source` 表示该机构是当前文件的分发来源，不把它等同于所有字段的原始制定机构。公开 Release 前必须从下载页面或随附说明补齐来源 URL 和权利依据；在此之前允许本地构建，不允许公开分发数据 artifact。

---

# 18. Manifest

每次构建都生成独立：

```text
manifest.json
```

Manifest 相当于：

> Dataset 的 `package.json + build provenance`。

Manifest 是 Release 的机器可读事实，不使用模糊的单个 `version`。建议模型：

```json
{
  "schemaVersion": 1,

  "release": {
    "id": "nhsa-drugs@2026-01-09.r1",
    "sequence": 1,
    "storageKey": "2026-01-09.r1",
    "buildRevision": 1,
    "createdAt": "<RFC3339 UTC>",
    "supersedes": null,
    "revoked": false
  },

  "dataset": {
    "id": "nhsa-drugs",
    "sourceVersion": "2026-01-09",
    "datasetSchemaVersion": 1,
    "status": "experimental"
  },

  "sources": [
    {
      "authority": "江西省医疗保障局",
      "authorityRole": "distribution-source",
      "authorityVerified": false,
      "format": "xlsx",
      "acquisition": "manual-local",
      "originalFilename": "江西省医保药品分类与代码数据库更新表(数据更新至2026年1月9日).xlsx",
      "sourceUrl": null,
      "acquiredAt": null,
      "publishedAt": null,
      "dataAsOf": "2026-01-09",
      "sha256": "9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67",
      "sizeBytes": 39514965,
      "worksheet": "总表",
      "recordCount": 269110,
      "columnCount": 26,
      "containerMetadata": {
        "createdAt": "2026-02-08T15:36:00Z",
        "modifiedAt": "2026-02-25T03:38:40Z",
        "zipEntryCount": 20,
        "uncompressedSizeBytes": 320670713,
        "externalLinkTargets": ["发挂网版_20260205.xlsx"]
      },
      "retention": "private-content-addressed",
      "sourceReacquirable": false,
      "reproducibleFromSource": true
    }
  ],

  "compiler": {
    "name": "cn-health-compiler",
    "version": "0.1.0",
    "adapter": "nhsa-drugs",
    "adapterVersion": 1,
    "gitCommit": "<full commit SHA>",
    "lockSha256": "<uv.lock SHA256>",
    "configSha256": "<workbook.yaml SHA256>",
    "buildInputSha256": "<ordered input digest>",
    "pythonVersion": "<exact version>",
    "sqliteVersion": "<exact version>"
  },

  "canonical": {
    "serialization": "canonical-ndjson-v1",
    "recordCount": 269110,
    "sha256": "<canonicalSha256>"
  },

  "artifacts": [
    {
      "name": "data.sqlite",
      "url": "data.sqlite",
      "mediaType": "application/vnd.sqlite3",
      "sha256": "<generated>",
      "sizeBytes": 0
    },
    {
      "name": "data.sqlite.zst",
      "url": "data.sqlite.zst",
      "mediaType": "application/zstd",
      "compression": "zstd",
      "sha256": "<generated compressed SHA256>",
      "sizeBytes": 0,
      "uncompressedName": "data.sqlite",
      "uncompressedSha256": "<same as data.sqlite SHA256>",
      "uncompressedSizeBytes": 0
    }
  ],

  "validation": {
    "passed": true,
    "report": "validation.json",
    "sha256": "<generated>"
  },

  "diff": {
    "report": "diff.json",
    "sha256": "<generated>"
  },

  "rights": {
    "redistribution": "review-required",
    "releaseEligible": false,
    "evidence": null
  },

  "runtime": {
    "minimumCliVersion": "0.2.0",
    "minimumSQLiteVersion": "3.34.0"
  }
}
```

Manifest 中的每个 artifact 都必须分别记录传输字节和解压后字节的哈希与大小。CLI 下载 `data.sqlite.zst` 时先校验压缩文件，再在有大小上限的临时目录中解压并校验 SQLite；不得使用 `data.sqlite` 的哈希直接校验 `.zst`。

示例中的 `retention: private-content-addressed` 和 `reproducibleFromSource: true` 只有在 Source Snapshot 已实际复制到受控私有存储并通过回读哈希后才成立。若文件只存在于可随时清理的 `tmp/`，构建器必须写 false，不能照抄示例。

## 18.1 Registry Index 与信任根

`dataset list`、`install` 和 `update` 读取一个独立、版本化的 `registry.json`。Registry 至少提供：

```json
{
  "schemaVersion": 1,
  "generatedAt": "<RFC3339 UTC>",
  "datasets": {
    "example-dataset": {
      "recommendedRelease": "example-dataset@2026-01-01.r1",
      "releases": [
        {
          "id": "example-dataset@2026-01-01.r1",
          "sequence": 1,
          "storageKey": "2026-01-01.r1",
          "sourceVersion": "2026-01-01",
          "buildRevision": 1,
          "manifestUrl": "<HTTPS URL>",
          "manifestSha256": "<SHA256>",
          "revoked": false
        }
      ]
    }
  },
  "signature": {
    "algorithm": "Ed25519",
    "keyId": "<trusted key id>",
    "url": "registry.json.sig"
  }
}
```

CLI 必须固定允许的 Registry Origin。无人值守远程安装前，Registry 还必须具有由 CLI 信任公钥验证的 detached signature，并定义密钥轮换方式。Manifest 与 artifact 同时从同一未认证位置下载时，Manifest 内的 SHA256 只能发现传输损坏，不能抵抗二者一起被替换。

Manifest 中的相对 artifact URL 以已验证的 Manifest URL 为基准解析；解析后仍必须属于允许的 Registry Origin。Local Manifest 则以 Manifest 所在目录为基准，禁止绝对路径和 `..`。

当前 `nhsa-drugs` Manifest 的 `releaseEligible` 为 false，因此它使用本地 Candidate 安装路径；上面的 `example-dataset` 只展示 Registry 结构。

---

# 19. 版本维度必须分开

不要使用一个 version 表达所有东西。

至少存在以下独立维度：

## Source Version

例如：

```text
2026-01-09
LOINC 2.83
NHC Clinical 2022
```

由数据源决定。当前药品基线取 XLSX 文件名声明的 `2026-01-09`，不得因为 Parser 修复而改变。

---

## Build Revision

同一个 Source Version 因 Parser、Normalization 或打包修复重新构建时递增：

```text
1
2
3
```

Build Revision 是整数，必须参与 Release 选择和本地存储路径。

---

## Release ID

Release ID 是不可变、不复用的组合标识，例如：

```text
nhsa-drugs@2026-01-09.r1
nhsa-drugs@2026-01-09.r2
```

CLI 不解析 Release ID 或 Source Version 字符串判断新旧，而是按 Registry 中每个 Dataset 单调递增的数值型 `sequence` 选择；Build Revision 仍作为审计字段。不得使用 SemVer build metadata 的优先级语义表达修订顺序。

`storageKey` 是经过 schema 验证的 ASCII 路径段，不等于任意 Source Version 原文。当前药品可使用 `2026-01-09.r1`；任何 ID、version 或 storageKey 都必须拒绝 `/`、`\`、`..`、控制字符和绝对路径形式。

---

## Compiler Version

例如：

```text
cn-health-compiler 0.4.1
```

使用 SemVer。

---

## Dataset Schema Version

例如：

```text
drug schema v3
```

它描述 canonical table 的兼容性。

---

## Manifest Schema Version

Manifest 顶层 `schemaVersion` 只描述 Manifest 自身，不替代 Dataset Schema Version。

这些维度必须同时写入 Manifest。Compiler 版本、Git commit、依赖锁摘要和配置摘要共同描述构建实现，但都不能替代 Release ID。

---

# 20. Build Pipeline

标准 Pipeline：

```text
Resolve Source
   ↓
Snapshot + Hash
   ↓
Inspect
   ↓
Extract
   ↓
Normalize
   ↓
Validate
   ↓
Diff
   ↓
Build SQLite
   ↓
Artifact Validation
   ↓
Optimize + Compress
   ↓
Manifest
   ↓
Distribution Gate
   ↓
Release
```

每一步职责明确。`nhsa-drugs` 首版从显式本地路径 Resolve，不包含 Discover 或 Download；其他 Dataset 以后可以在 Resolve Source 内实现远程发现，但不能改变后续契约。

---

# 21. Resolve Source

负责把用户明确选择的输入解析为不可变的 Source 描述。

当前药品构建命令必须显式接收文件：

```bash
uv run cn-health-build build nhsa-drugs \
  --source "$DRUG_SOURCE"
```

输出：

```python
SourceInput(
    dataset_id="nhsa-drugs",
    source_version="2026-01-09",
    acquisition="manual-local",
    path=...,
    original_filename=...,
    source_url=None,
    expected_sha256="9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67",
    worksheet="总表",
)
```

Compiler 不扫描 `tmp/` 猜测最新文件，也不把同目录的 PDF 当作补充来源。文件名、声明日期和 expected SHA256 任一不符合 Contract 时都必须停止。

其他 Dataset 若以后实现远程发现，Source 描述仍必须包含最终 URL、发现页面、来源版本和预期来源域名。不能只比较页面上的版本字符串；同版本附件也必须通过内容哈希检测变化。

---

# 22. Snapshot Source

职责单一：

```text
explicit local source
        ↓
stable build snapshot
```

Snapshot 阶段：

- 以只读方式打开输入；
- 在任何解析前计算 size 和 SHA256；
- 与 Dataset Contract 的 expected SHA256 比较；
- 可复制到 `.work/sources/<sha256>/source.xlsx`，确保长构建期间输入不变；
- 复制前后再次比较 size 和 SHA256，防止读取过程中被替换；
- 记录原始文件名、取得方式和本地取得时间；
- 不解析业务字段，不解析或下载外部链接。

当前基线的 expected SHA256 是：

```text
9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67
```

---

# 23. Inspect

这是非常重要但经常被忽视的阶段。

用于回答：

```text
文件格式是什么？
有哪些 sheet？
目标 sheet 的 dimension 是什么？
有哪些 columns？
表头是什么？
是否存在公式？
是否存在 external links？
ZIP container 是否完整？
```

对当前药品基线，Inspect 必须确认：

```text
Workbook sheets:
  西药中成药新增变更
  本省双通道
  总表

Canonical sheet: 总表
Dimension: A1:Z269111
Header row: 1
Data rows: 269110
Columns: 26
Formula cells in 总表: 0
```

工作簿包含指向 `发挂网版_20260205.xlsx` 的 external link。Compiler 必须禁用 external link 解析和刷新；canonical `总表` 不依赖公式缓存。

OOXML metadata 显示容器创建时间为 `2026-02-08T15:36:00Z`、修改时间为 `2026-02-25T03:38:40Z`。这些是文件容器元数据，不覆盖文件名声明的 `dataAsOf=2026-01-09`；三者都写入 Provenance，避免把文件修改时间误当 Dataset Version。

Inspect 失败意味着：

> 不应继续执行 Parser。

---

# 24. Extract

负责：

```text
原始格式
   ↓
raw records
```

这一阶段尽量保持原始信息。

不要过早修改字段。

药品总表使用：

```python
RawDrugRow
```

每条 RawRow 至少保留：

```text
source_sheet = "总表"
source_row
raw_code
raw_registered_name
raw_trade_name
raw_registered_dosage_form
raw_registered_specification
raw_manufacturer
raw_approval_number
raw_market_status
```

Extractor 按表头名称读取，不依赖易错的裸列下标；但 Header Fingerprint 仍要求 26 列名称和顺序完全匹配。只遍历 `总表` 的第 2 至 269111 行，不把另外两个工作表拼接进 canonical records。

---

# 25. Normalize

负责从：

```text
Raw Model
```

转换为：

```text
Canonical Model
```

例如：

```text
去除无意义空格
人类可读文本使用 Unicode NFC normalization
空字符串 → null
日期 normalization
字段重命名
剂型基础规范化
代码格式检查
```

药品代码只允许去除首尾 ASCII 空白，之后必须按原值校验；不得对代码执行 NFKC、大小写猜测或字符替换。来源值与规范化值应可逐字段追溯。拼音、别名和 n-gram 是 Runtime Search Projection，不是 canonical source fact。

但不要未经明确规则：

```text
“智能修改”官方事实
```

---

# 26. Validation

医疗 Reference Data 必须采用：

> **Fail Closed**

而不是：

> “能解析多少就发布多少”。

每个 Dataset 应定义：

```text
minimum row count
required fields
unique keys
code pattern
null-rate threshold
duplicate threshold
value distributions
cross-field rules
```

例如：

```yaml
validation:
  source:
    sha256: 9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67
    worksheet: 总表
    header_columns: 26
    formula_cells: 0

  record_count:
    baseline: 269110
    min: 250000
    max_relative_decrease: 0.05
    max_relative_increase: 0.10

  required:
    - code
    - registered_name
    - data_source
    - market_status

  max_null_rate:
    code: 0
    registered_name: 0
    data_source: 0
    market_status: 0

  null_rate_drift:
    alert_absolute_delta: 0.02
    baseline:
      repackaging_company: 0.99451154
      previous_approval_number: 0.99507265
      marketing_authorization_holder: 0.15770503
      insurance_name: 0.35396678
      reimbursement_class_2025: 0.35396678
      insurance_dosage_form: 0.59032738
      insurance_number: 0.35396678
      note: 0.96180372
      former_code: 0.98136450

  unique:
    - code

  code:
    pattern: "^[A-Z0-9]+$"
    allowed_lengths: [20, 23]

  allowed_values:
    market_status:
      - 上市
      - 停产
      - 未上市
```

当前基线实测：

```text
269110 data rows
269110 unique drug codes
0 missing drug codes
0 missing registered names
0 formulas in 总表

market_status:
  上市    228388
  停产     30808
  未上市    9914
```

上述精确数字用于锁定当前 SHA256 对应的 baseline fixture。以后更换合法的新 Source 时，应更新 baseline 并与上一 Release 做相对变化检查；超过阈值只能通过带理由的人工 override，不能自动放行。

---

# 27. Diff

每次更新都应该和上一版比较。

输出：

```json
{
  "baseRelease": "nhsa-drugs@2026-01-09.r1",
  "targetRelease": "nhsa-drugs@2026-01-09.r2",
  "baseSourceSha256": "<SHA256>",
  "targetSourceSha256": "<SHA256>",
  "added": 1283,
  "removed": 17,
  "modified": 382,
  "unchanged": 267428,
  "modifiedFields": {
    "market_status": 42,
    "specification": 191
  }
}
```

Diff 必须明确 base 和 target Release，不能只写两个 source version。来源版本字符串相同但 SHA256 不同时，仍视为同一 Source Version 下新的 Source Snapshot，需要人工确认后分配新的 Build Revision；旧 Release 保持不变，具体输入由 `sources[].sha256` 区分。

将 Dataset 管理逐渐演化为：

> **Reference Data Version Control。**

---

# 28. 为什么默认 Full Rebuild

初期即使：

```text
20万
100万
600万
```

条记录，对本地数据工程都不是不可接受的规模。

相比复杂 incremental mutation：

```text
锁定一个 Source Snapshot
→ 完整构建
→ validate
→ diff
→ publish immutable snapshot
```

更加：

- 简单；
- 可重复；
- 可审计；
- 不容易积累历史错误。

只有未来确实存在性能瓶颈时，再引入 incremental build。

---

# 29. NHSA Drugs Source Strategy

`nhsa-drugs` 首版只采用调用方显式指定、且匹配以下身份的 Source Snapshot：

```text
<DRUG_SOURCE>
```

关键身份：

```text
Source Version: 2026-01-09
Size: 39514965 bytes
SHA256: 9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67
Canonical Sheet: 总表
```

该选择意味着首版明确不做：

```text
discover_latest() on NHSA website
official PDF download
PDF table extraction
XLSX/PDF reconciliation
automatic upstream synchronization
```

`tmp/` 中的 2026-08-14 PDF 不参与 canonical build、交叉补全或版本判断。它可以保留为人工研究材料，但 Compiler 不读取它。

当前输入是一个声明日期的分发快照，因此 Manifest 准确记录 distribution source 和 `dataAsOf`；项目不将它描述成实时同步的全国最新数据。

---

# 30. NHSA 药品 XLSX Compiler

专门建立：

```text
NhsaDrugXlsxAdapter
```

生命周期：

```text
resolve_explicit_source()
snapshot()
inspect_workbook()
fingerprint()
extract_total_sheet()
normalize()
validate()
diff()
build_sqlite()
package()
```

Adapter 不实现网络发现、PDF 解析或 OCR。XLSX 读取使用只读/流式模式，禁止刷新 external links，避免把 39.5 MB 压缩包整体展开到内存中的对象模型。

使用 openpyxl 时至少采用：

```python
load_workbook(
    source_path,
    read_only=True,
    data_only=False,
    keep_links=False,
)
```

`data_only=False` 用于识别并拒绝公式，而不是悄悄消费公式缓存；`keep_links=False` 防止保留或追踪外部工作簿关系。

---

# 31. 只读取 `总表`

Workbook 包含：

```text
西药中成药新增变更    A1:AH3103
本省双通道            A1:AN1372
总表                  A1:Z269111
```

首版 canonical records 只来自 `总表`。理由：

- `总表` 已提供完整快照；
- 另外两个工作表的字段布局不同，属于变更/省级辅助视图；
- 再次合并会产生重复、覆盖顺序和省级语义泄漏；
- canonical build 应重建完整快照，而不是回放来源工作簿内部的增量视图。

如果以后需要发布“双通道”或变更记录，应建立独立 Dataset 或 projection，不修改 `nhsa-drugs` 总表语义。

---

# 32. XLSX 行提取

读取规则：

```text
row 1       exact header
row 2..end data rows
empty text  null during normalization
formula     reject in canonical sheet
external link resolution disabled
```

每一行按 header name 映射为 RawDrugRow，并保留 `source_row`。单元格中的显示字符串按来源值读取；不自动执行 Excel 公式、不刷新链接、不依据格式化外观猜测数值。

当前 `总表` 实测没有公式。工作簿容器存在一个指向 `发挂网版_20260205.xlsx` 的 external link，但该链接不属于构建输入。若未来 `总表` 出现公式或公式依赖外部工作簿，Inspect 必须失败，而不是使用不透明的缓存结果。

---

# 33. `workbook.yaml`

Workbook Contract 不硬编码散落在 Python 中。当前基线：

```yaml
version: 1

source:
  filename: 江西省医保药品分类与代码数据库更新表(数据更新至2026年1月9日).xlsx
  sha256: 9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67
  size_bytes: 39514965

workbook:
  required_sheets:
    - 西药中成药新增变更
    - 本省双通道
    - 总表
  canonical_sheet: 总表
  resolve_external_links: false

container:
  expected_zip_entries: 20
  expected_uncompressed_size_bytes: 320670713
  max_uncompressed_size_bytes: 400000000
  reject_macros: true

sheet:
  dimension: A1:Z269111
  header_row: 1
  first_data_row: 2
  expected_data_rows: 269110
  expected_formula_cells: 0
  headers:
    - 药品代码
    - 数据来源
    - 注册名称
    - 商品名称
    - 注册剂型
    - 剂型
    - 注册规格
    - 规格
    - 包装材质
    - 最小包装数量
    - 最小制剂单位
    - 最小包装单位
    - 药品企业
    - 分包装企业名称
    - 生产企业
    - 批准文号
    - 原批准文号
    - 药品本位码
    - 上市药品持有人
    - 市场状态
    - 医保药品名称
    - 2025版甲乙类
    - 医保剂型
    - 编号
    - 备注
    - 曾用码
```

新 Source 版本需要新的基线时，更新 `workbook.yaml` 并提升其 version；其内容摘要写入 Manifest。不能只改 Python 代码绕过 fingerprint。

可维护：

```text
workbook-v1.yaml
workbook-v2.yaml
```

---

# 34. XLSX Workbook Fingerprint

完整遍历前先检查：

```text
ZIP container integrity
source size and SHA256
required sheet names
canonical sheet dimension
exact ordered headers
formula count
external link policy
sample row shape
```

当前 SHA256 必须与已知 baseline 完全一致。引入新 Source 时，即使文件名或 `dataAsOf` 没变，也必须先比较 SHA256；任何结构变化都应：

```text
BUILD FAILED
SOURCE FORMAT CHANGED
```

ZIP entry 数和声明的总解压大小必须在解压前检查，并受 `max_uncompressed_size_bytes` 限制。Parser 直接读取 OOXML container，不把成员按其内部路径写到文件系统。任何宏、异常路径、加密成员或超限成员都 fail closed，而不是继续产生错误数据。

---

# 35. SQLite Schema 原则

不要强迫所有 Dataset 使用一个万能：

```text
concept
```

表。

应：

> **Domain-specific tables + common metadata。**

例如药品：

```sql
CREATE TABLE drug (
    code TEXT PRIMARY KEY,
    data_source TEXT NOT NULL,
    registered_name TEXT NOT NULL,
    trade_name TEXT NOT NULL,
    registered_dosage_form TEXT NOT NULL,
    dosage_form TEXT NOT NULL,
    registered_specification TEXT NOT NULL,
    specification TEXT NOT NULL,
    packaging_material TEXT NOT NULL,
    minimum_package_quantity TEXT NOT NULL,
    minimum_dosage_unit TEXT NOT NULL,
    minimum_package_unit TEXT NOT NULL,
    drug_company TEXT NOT NULL,
    repackaging_company TEXT,
    manufacturer TEXT NOT NULL,
    approval_number TEXT NOT NULL,
    previous_approval_number TEXT,
    standard_drug_code TEXT NOT NULL,
    marketing_authorization_holder TEXT,
    market_status TEXT NOT NULL
        CHECK (market_status IN ('上市', '停产', '未上市')),
    insurance_name TEXT,
    reimbursement_class_2025 TEXT,
    insurance_dosage_form TEXT,
    insurance_number TEXT,
    note TEXT,
    former_code TEXT,
    source_row INTEGER NOT NULL UNIQUE,
    source_version TEXT NOT NULL,
    source_sha256 TEXT NOT NULL
);
```

字段映射必须在 Dataset Contract 中逐项记录：

| `总表` 字段 | Canonical column |
|---|---|
| 药品代码 | `code` |
| 数据来源 | `data_source` |
| 注册名称 | `registered_name` |
| 商品名称 | `trade_name` |
| 注册剂型 | `registered_dosage_form` |
| 剂型 | `dosage_form` |
| 注册规格 | `registered_specification` |
| 规格 | `specification` |
| 包装材质 | `packaging_material` |
| 最小包装数量 | `minimum_package_quantity` |
| 最小制剂单位 | `minimum_dosage_unit` |
| 最小包装单位 | `minimum_package_unit` |
| 药品企业 | `drug_company` |
| 分包装企业名称 | `repackaging_company` |
| 生产企业 | `manufacturer` |
| 批准文号 | `approval_number` |
| 原批准文号 | `previous_approval_number` |
| 药品本位码 | `standard_drug_code` |
| 上市药品持有人 | `marketing_authorization_holder` |
| 市场状态 | `market_status` |
| 医保药品名称 | `insurance_name` |
| 2025版甲乙类 | `reimbursement_class_2025` |
| 医保剂型 | `insurance_dosage_form` |
| 编号 | `insurance_number` |
| 备注 | `note` |
| 曾用码 | `former_code` |

首版优先忠实保存来源文本；`最小包装数量` 暂以 TEXT 保存原值，另有明确且覆盖异常值的规则后再增加派生数值列。来源中的字面值 `无` 不是空值，不得自动转成 null。

疾病：

```sql
CREATE TABLE diagnosis (
    code TEXT PRIMARY KEY,

    name TEXT NOT NULL,
    parent_code TEXT,
    category TEXT,

    source_version TEXT NOT NULL
);
```

---

# 36. Mapping

映射关系单独建模。

例如：

```text
SNOMED → ICD-CN
RxNorm → Chinese Drug
NMPA → NHSA
```

推荐：

```sql
CREATE TABLE terminology_mapping (
    mapping_version TEXT NOT NULL,
    source_system TEXT NOT NULL,
    source_code TEXT NOT NULL,

    target_system TEXT NOT NULL,
    target_code TEXT NOT NULL,

    relation TEXT NOT NULL,

    confidence REAL CHECK (confidence BETWEEN 0.0 AND 1.0),
    method TEXT NOT NULL,
    review_status TEXT NOT NULL,
    provenance_id TEXT NOT NULL,
    evidence_uri TEXT,
    reviewer TEXT,
    reviewed_at TEXT,

    PRIMARY KEY (
        mapping_version,
        source_system,
        source_code,
        target_system,
        target_code
    )
);
```

Mapping 不能简单当成：

```text
translation dictionary
```

应保存：

```text
relation
method
provenance
review status
```

`provenance_id` 指向独立 provenance record。Mapping 的新版本新增行或新 artifact，不原地覆盖旧 relation、confidence 或 review 结果。

---

# 37. Search

Exact lookup 和全文搜索必须分开。

## Exact

```sql
SELECT *
FROM drug
WHERE code = ?;

CREATE INDEX drug_approval_number_idx ON drug(approval_number);
CREATE INDEX drug_standard_code_idx ON drug(standard_drug_code);
```

建立 B-tree。

---

## Search

例如：

```text
二甲双胍
糖尿病
糖化血红蛋白
```

中文包含搜索使用 FTS5 `trigram` tokenizer，而不是未分词的默认 `unicode61`：

```sql
CREATE VIRTUAL TABLE drug_fts USING fts5(
    registered_name,
    trade_name,
    insurance_name,
    manufacturer,
    content = 'drug',
    content_rowid = 'rowid',
    tokenize = 'trigram'
);

INSERT INTO drug_fts(
    rowid,
    registered_name,
    trade_name,
    insurance_name,
    manufacturer
)
SELECT
    rowid,
    registered_name,
    trade_name,
    insurance_name,
    manufacturer
FROM drug
ORDER BY code;
```

默认 tokenizer 会把连续中文名称当作一个 token。例如索引“盐酸二甲双胍片”后，默认 FTS5 不保证“二甲双胍”命中；`trigram` 可以支持该类三字符以上 substring 查询。Runtime 因此要求 SQLite `>= 3.34.0`，并在启动时验证 FTS5 和 trigram 可用。

查询契约：

- 默认把用户输入作为 literal，不直接暴露 FTS5 查询语法；
- 三个及以上 Unicode 字符使用 trigram；
- 两个中文字符可使用预生成 bigram 候选表，再以 `instr()` 对候选集复核；
- 单字符包含搜索默认拒绝，避免无界结果；
- 默认 `limit=20`，最大 `limit=200`；
- 排序固定为相关性、`code`，相同输入和 Release 必须稳定；
- 药品代码、批准文号等标识符走 B-tree exact/prefix lookup。

两字符候选表可以使用：

```sql
CREATE TABLE drug_search_bigram (
    term TEXT NOT NULL,
    code TEXT NOT NULL REFERENCES drug(code),
    PRIMARY KEY (term, code)
) WITHOUT ROWID;
```

它只保存 Runtime Projection 生成的去重 bigram，查询先按 `term` 命中候选 code，再对候选字段做 literal 复核。

不得直接对 269,110 行执行无界全表：

```sql
LIKE '%xxx%'
```

---

# 38. 中文搜索扩展

可在 Runtime Search Projection 构建阶段生成：

```text
pinyin
pinyin_compact
initials
aliases
```

例如：

```text
盐酸二甲双胍片

yansuanerjiashuangguapian
ysejsgp
```

未来 CLI 可以支持：

```bash
cn-health drug search 二甲双胍

cn-health drug search erjiashuanggua

cn-health drug search ejsg
```

拼音存在多音字和实现版本差异，因此派生字段必须记录生成器版本，并与 canonical source columns 分表存储。该能力不是 v0.1 必需，可以后置。

---

# 39. SQLite Artifact Build

构建时固定 page size、`application_id`、`user_version`、SQLite 版本和创建顺序。Release 前在无并发连接的情况下：

```sql
ANALYZE;
PRAGMA optimize;
VACUUM;
PRAGMA journal_mode = DELETE;
PRAGMA integrity_check;
```

建立所有：

```text
PRIMARY KEY
INDEX
FTS
```

之后再发布。

`integrity_check` 必须精确返回 `ok`。关闭连接后确认只存在 `data.sqlite`，不存在 `data.sqlite-wal`、`data.sqlite-shm` 或 journal sidecar，再计算未压缩 SHA256 和执行 zstd 压缩。

用户拿到的必须是：

> **Ready-to-query database。**

Runtime 默认以 read-only 模式打开已验证 artifact，不对 Release 数据库执行 migration、自动建索引或写入搜索缓存。需要可变缓存时放在独立文件中。

---

# 40. Parquet

SQLite 是 Runtime Artifact。

Parquet 是 Analytics Artifact。

典型消费者：

```text
DuckDB
Polars
Python
Spark
Research
```

第一阶段可以：

```text
SQLite required
Parquet optional
```

后期大型 Dataset 建议同时提供。

---

# 41. Release Artifact

本地 Candidate Artifact 例如：

```text
nhsa-drugs
└── releases
    └── 2026-01-09.r1
        ├── data.sqlite
        ├── data.sqlite.zst
        ├── data.parquet
        ├── manifest.json
        ├── validation.json
        └── diff.json
```

目录由 Source Version 和数值型 Build Revision 共同寻址。`manifest.json` 中必须存在每个实际发布文件的 size 和 SHA256；如果 Parquet 未生成，就不能在 Manifest 中声明。

Candidate 默认保留在本地 `dist/`。进入可选远程分发通道时，Registry 根据 Manifest 的分发元数据、签名和其余 Release Gate 选择 Release。

不包含：

```text
官方 PDF
官方 XLSX
网页镜像
```

---

# 42. Immutable Release

任何已经发布的 Release，例如未来通过全部门禁的：

```text
nhsa-drugs@2026-01-09.r1
```

就不应该覆盖。

发现 Parser bug 时：

```text
nhsa-drugs@2026-01-09.r1  保留
nhsa-drugs@2026-01-09.r2  新建
```

如果来源数据真正更新：

```text
nhsa-drugs@<new-source-version>.r1
```

Release ID、Manifest URL 和 artifact URL 一经发布不得复用。发现严重问题时，在 Registry 中将旧 Release 标记 `revoked: true` 并指向替代版本；不得删除身份后用新内容占据旧 URL。

Compiler version 和 artifact hash 用于审计，不能代替 Build Revision，也不能作为覆盖旧目录的理由。

---

# 43. CLI

最终用户入口：

```text
cn-health
```

第一版命令建议：

```bash
cn-health dataset list

cn-health dataset install loinc-zh-cn

cn-health dataset install nhc-icd10-clinical

cn-health dataset install nhsa-drugs

cn-health dataset info nhsa-drugs

cn-health update
```

`cn-health dataset install nhsa-drugs` 从公开 Registry 安装时选择 `releaseEligible: true` 的 Release；当前基线使用显式本地 Candidate 安装流程，两条路径互不改变对方的分发元数据。

查询：

```bash
cn-health diagnosis search "糖尿病"

cn-health drug search "二甲双胍"

cn-health loinc search "糖化血红蛋白"
```

精确：

```bash
cn-health drug get <code>
```

Agent：

```bash
cn-health drug search "阿莫西林" --json
```

## 43.1 JSON Contract

`--json` 是版本化接口，不是人类输出的序列化副本。成功响应：

```json
{
  "schemaVersion": 1,
  "command": "drug.search",
  "dataset": {
    "id": "nhsa-drugs",
    "releaseId": "nhsa-drugs@2026-01-09.r1"
  },
  "query": {
    "text": "二甲双胍",
    "mode": "literal",
    "limit": 20
  },
  "items": [
    {
      "code": "<drug code>",
      "registeredName": "盐酸二甲双胍片",
      "tradeName": "<source value>",
      "marketStatus": "上市",
      "rank": 1
    }
  ],
  "page": {
    "returned": 1,
    "limit": 20,
    "truncated": false
  }
}
```

错误响应也保持 JSON：

```json
{
  "schemaVersion": 1,
  "error": {
    "code": "DATASET_NOT_INSTALLED",
    "message": "Dataset nhsa-drugs is not installed"
  }
}
```

接口规则：

- stdout 只输出一个 UTF-8 JSON object，不带 ANSI、进度条或日志；
- 诊断和进度写 stderr；
- 无结果是 exit code `0` 且 `items: []`；
- 参数错误为 `2`，Dataset 缺失或不兼容为 `3`，Registry/artifact 校验失败为 `4`，其他 Runtime 错误为 `5`；
- 新增 optional field 可以保持同一 schemaVersion，删除字段或改变语义必须提升 schemaVersion；
- TS prototype 与 Rust Runtime 必须对同一组 JSON golden tests 产生兼容输出。

---

# 44. CLI Local Storage

建议使用操作系统标准数据目录。

概念上：

```text
~/.local/share/cn-health/
```

Windows 使用对应的用户 Local App Data。

结构：

```text
cn-health/
├── datasets/
│   ├── nhsa-drugs/
│   │   ├── releases/
│   │   │   └── 2026-01-09.r1/
│   │   │       ├── data.sqlite
│   │   │       └── manifest.json
│   │   └── current.json
│   │
│   └── loinc-zh-cn/
│
├── locks/
├── tmp/
└── config.json
```

`current.json` 不依赖 Unix symlink，因而可跨平台使用：

```json
{
  "releaseId": "nhsa-drugs@2026-01-09.r1",
  "sequence": 1,
  "storageKey": "2026-01-09.r1",
  "sourceVersion": "2026-01-09",
  "buildRevision": 1,
  "relativePath": "releases/2026-01-09.r1"
}
```

更新时先写同目录临时文件、flush/fsync，再用原子 rename 替换 `current.json`。Runtime 每次打开数据库前读取一次完整 pointer，不观察中间状态。

---

# 45. Dataset Install

用户：

```bash
cn-health dataset install nhsa-drugs
```

执行：

```text
acquire per-dataset install lock
       ↓
读取并验证 signed Registry
       ↓
选择未 revoked 且兼容的 Release
       ↓
下载 Manifest 并验证 Registry 中的 manifestSha256
       ↓
检查 rights.releaseEligible 和 runtime compatibility
       ↓
下载 data.sqlite.zst 到同文件系统临时目录
       ↓
校验 compressed size + SHA256
       ↓
按 uncompressedSizeBytes 上限流式解压
       ↓
校验 uncompressed size + SHA256
       ↓
SQLite integrity_check + application checks
       ↓
fsync + atomic rename 到 releases/<storageKey>
       ↓
atomic replace current.json
       ↓
release lock + cleanup temp
```

安装约束：

- 临时目录与最终目录必须在同一文件系统，保证 rename 原子性；
- 下载、压缩和解压都设置超时、最大字节数和磁盘余量检查；
- artifact 名称来自 Manifest 白名单，不能形成绝对路径或 `..` 路径穿越；
- 同一 Release 已存在时，必须重新核对 Manifest 和 SQLite hash，不得原地覆盖；
- 任何一步失败时保留旧 `current.json`，删除或隔离临时文件；
- 进程崩溃后可安全重试，并清理不再被锁持有的过期临时目录。

本地开发可以使用：

```bash
cn-health dataset install --local-manifest \
  dist/nhsa-drugs/releases/2026-01-09.r1/manifest.json
```

`--local-manifest` 用于安装调用方持有的本地 Candidate；它仍执行双重哈希和 SQLite 完整性检查，将来源标记为 `local-untrusted`，且不参与自动 update。远程 Registry 独立选择 `releaseEligible: true` 的 Release，本地安装不会修改 Registry 元数据。

---

# 46. npm Distribution

最终希望支持：

```bash
npx cn-health
```

但 npm package 不应该重新实现 Runtime。

npm 包：

```text
detect OS
detect architecture
locate native binary
exec
```

Rust binary 独立预编译：

```text
Windows x64
Linux x64
Linux ARM64
macOS ARM64
macOS x64
```

类似现代 native npm 工具的分发方式。

---

# 47. 第一阶段不要急着 Rust 化

建议真实开发顺序：

## Stage A

```text
Python Compiler
      ↓
SQLite
```

证明 Data Pipeline。

---

## Stage B

使用熟悉的 TypeScript 快速 prototype CLI：

```text
pnpm
better-sqlite3
commander
```

验证：

```text
命令结构
输出格式
JSON contract
Dataset Manager UX
```

---

## Stage C

接口稳定以后：

```text
Rust rewrite
```

Rust 负责：

```text
fast startup
single binary
portable runtime
low memory
distribution
```

---

# 48. Data Rights

代码许可证和数据权利必须分离。

```text
LICENSE
```

采用标准 MIT License，只覆盖项目贡献者自行创作的软件代码和原创项目文档，除非具体
文件另有说明。它默认不覆盖原始来源数据、第三方逐条数据、由第三方数据生成的 SQLite、
Parquet、Mapping 等数据 artifact，也不覆盖第三方名称、Logo 或商标。

项目不拥有、也不主张拥有这些第三方医疗健康数据，不能通过根目录 MIT License 授予
自己并不拥有的权利。

第三方数据通过：

```text
DATA-NOTICE.md
```

说明。

不得暗示：

> 项目可以替原发布方将第三方数据重新授权为 MIT / Apache。

数据是否是“事实”、是否经过格式转换，与来源条款是两个问题。每个 Source 的 Contract 独立记录可审计的条款元数据、证据、署名和适用 artifact 类型。

当前声明的药品工作簿用于本地 Parser 开发和验证，其 Manifest 如实记录当前分发配置：

```text
rights.redistribution = review-required
rights.release_eligible = false
```

该配置使本地 Candidate 与远程 Registry Release 保持为两条独立路径。

---

# 49. 数据发布原则

在权利允许时，项目主要发布：

> **Normalized factual dataset。**

而不是：

```text
政府网页镜像
官方 PDF 镜像
官方 Logo
文章正文
完整网站
```

每个 Source 在 `dataset.yaml` 明确：

```yaml
rights:
  redistribution: review-required
  release_eligible: false
  legal_basis: null
  evidence: []
  allowed_artifacts: []
  attribution: null
  reviewed_by: null
  reviewed_at: null
```

`redistribution` 取值及含义：

| Value | Public release behavior |
|---|---|
| `public` | 可按证据允许的方式发布原始或派生 artifact |
| `normalized-only` | 只能发布明确获准的规范化 artifact，不发布原文件 |
| `metadata-only` | 只发布 Manifest、字段说明和统计，不发布逐条数据 |
| `private` | 仅限私有构建和授权环境 |
| `review-required` | 尚未配置远程逐条数据 artifact，使用本地 Candidate 或 metadata workflow |

`release_eligible` 由 Distribution Gate 根据 evidence 和 allowed artifacts 计算，构建命令的普通 flag 不修改这项 Manifest 元数据。

---

# 50. Takedown 与 Rights Handling

项目 README / DATA-NOTICE 应明确：

- 第三方原始数据权利归原权利主体；
- 项目不主张对原始数据拥有排他权利；
- 项目主要提供格式转换、标准化、索引和版本管理；
- 保留来源和版本信息；
- 权利主体提出合理要求后，可采取：
  - 补充署名；
  - 修改分发方式；
  - 限制访问；
  - 下架相关 Dataset。

但应认识到：

> Takedown 声明本身并不是法律授权。

因此仍应逐 Source 记录权利状态。

Takedown 或权利变化发生时：

- 在 Registry 将受影响 Release 标记为 `revoked` 并写明 reason、时间和替代 Release；
- 停止新的自动安装；
- 按法律或权利要求移除远程 artifact，但保留不公开的审计元数据；
- CLI 对已安装版本显示警告，不未经用户同意删除本地文件；
- 重新发布时使用新的 Release ID，不复用被撤回 URL。

---

# 51. Provenance

至少保存：

```text
authority
authority role
acquisition method
original filename
source URL / discovery page（如有）
publication date
effective/data-as-of date
file SHA256
file size
sheet info / exact header fingerprint
compiler version
adapter version
compiler git commit
dependency lock SHA256
schema/config/mapping SHA256
record count
all artifact SHA256 values
rights evidence
raw source retention status
```

Manifest 使用 `sources[]`，因为一个 Dataset 可能依赖多个文件、语言包或 Mapping。每个输入独立记录上述信息，顺序也纳入 build input digest。

SHA256 只能证明“拿到的文件是否与当时相同”，不能在上游文件消失后恢复内容。要声明可重复构建，必须在权利允许的私有环境中按内容寻址保留 Source Snapshot，或确认外部来源具有稳定、可再次取得的不可变 URL。

如果原文件未保留且无法稳定重新取得，Manifest 必须写：

```json
{
  "sourceReacquirable": false,
  "reproducibleFromSource": false
}
```

此时仍可追踪来源元数据，但不能声称完整复现。

---

# 52. Source Inventory

维护：

```text
docs/source-inventory.md
```

字段建议：

| Field | Meaning |
|---|---|
| Dataset ID | 唯一 ID |
| Authority | 权威机构 |
| Authority Role | 原始制定/分发/镜像角色 |
| Source | 发布入口 |
| Acquisition | manual-local/official-download/API |
| Format | PDF/XLSX/CSV |
| SHA256 | Source Snapshot 身份 |
| Size | 文件大小 |
| Record Count | 数据量 |
| Update Frequency | 更新频率 |
| Extraction | 解析方案 |
| Version | 当前版本 |
| Rights | 分发状态 |
| Rights Evidence | 许可、条款或审核依据 |
| Retention | 原文件是否私有保留或可再次取得 |
| Status | planned/experimental/stable |

---

# 53. Dataset Stability

建议 Dataset 状态：

```text
experimental
beta
stable
deprecated
```

例如：

```yaml
status: experimental
```

只有：

- Parser 稳定；
- 至少多版本测试；
- Schema 基本稳定；
- Validation 完整；
- Release 可重复；
- Provenance 和 Source Retention 状态完整；
- 来源条款元数据明确，公开 Release 满足 Distribution Gate；
- install/update/revocation 行为经过测试；

以后才进入：

```text
stable
```

---

# 54. Testing Strategy

至少覆盖四层测试。

## Parser Unit Tests

输入少量 fixture。

例如：

```text
XLSX with exact 总表 header
XLSX with reordered/missing header
XLSX with empty optional cells
XLSX with formula in canonical sheet
XLSX with duplicate drug code
```

验证：

```text
exact RawRow
```

---

## Normalization Tests

```text
RawRow
  ↓
CanonicalRecord
```

确定性测试。

---

## Dataset Validation Tests

针对整个输出：

```text
row count
unique keys
null rates
known concepts
code format
```

---

## Runtime Tests

例如：

```bash
cn-health drug search 二甲双胍
```

必须返回预期结果。

还必须覆盖：

```text
default FTS tokenizer does not satisfy substring contract
trigram matches 盐酸二甲双胍片 by 二甲双胍
two-character bigram candidate search
stable limit and ordering
JSON success/error golden output
missing/revoked/incompatible Dataset exit codes
```

---

# 55. Golden Fixtures

为 XLSX Parser 建立非常小的 synthetic fixture。

不要把 39.5 MB 来源工作簿提交 Git，也不要从其中裁剪数据后默认认为可以公开提交。

而是在允许的前提下维护：

```text
人工构造的最小测试 XLSX
```

Fixture 使用虚构药品代码和内容，只复制字段结构，不复制来源记录。

覆盖：

```text
normal row
literal 无 value
empty optional cell
exact 26-column header
missing/reordered header
missing cell
duplicate code
20/23-character code
formula rejection
external link disabled
long manufacturer
```

完整的 269,110 行 Source Snapshot 只用于受控 integration/release build；其 SHA256 和实测统计是 baseline，不是 PR fixture。

---

# 56. Reproducibility

可重复性分为两层：

## Canonical Reproducibility

相同 Build Input 必须产生相同的 canonical records。Build Input Digest 至少覆盖：

```text
ordered sources[] + every source SHA256
Dataset Schema SHA256
workbook/layout config SHA256
mapping and normalization asset SHA256
compiler version + full git commit
uv.lock SHA256
relevant build options
```

`canonical-ndjson-v1` 将 records 按 UTF-8 binary `code` 顺序排列，每条记录使用 RFC 8785 JSON Canonicalization Scheme 编码，行分隔固定为 LF，文件以一个 LF 结束。对这些字节生成 `canonicalSha256`，作为跨机器验证“数据内容相同”的主要依据。若更改序列化规则，必须使用新的 serialization ID。

## Artifact Reproducibility

要进一步产生字节完全相同的 SQLite 和 zstd artifact，还必须固定：


```text
sorting
Python and parser library versions
SQLite library version and compile options
PRAGMA/page size/application_id/user_version
SQLite creation order
locale and timezone
zstd version and compression parameters
SOURCE_DATE_EPOCH or other embedded timestamps
```

构建结束后必须关闭所有连接，确认没有 `-wal`、`-shm` 或 journal 文件，再计算 SQLite hash。Manifest 的实际构建时间属于构建事件元数据，可以不同；复现判断优先比较 Build Input Digest 和 `canonicalSha256`，只有使用完全固定工具链时才承诺 SQLite 字节哈希相同。

仅记录 `compiler version` 不足以锁定依赖和配置。原 Source 未保留且不可再次取得时，不得标记 `reproducibleFromSource: true`。

---

# 57. CI

CI 第一阶段主要运行：

```text
Python lint
Python typecheck
unit tests
schema validation
Rust test
pnpm test
small fixture dataset build
```

不要在每次 PR：

```text
读取完整 39.5 MB 药品 XLSX
重建几十万行数据库
```

当前药品 Dataset 的完整 Build 应使用：

```text
manual workflow
release workflow
```

CI 使用 synthetic XLSX fixture，不访问 `tmp/`，也不从官网获取药品 PDF。受控 full-build runner 必须显式提供匹配 expected SHA256 的 Source Snapshot。

---

# 58. Scheduled Update

当前 `nhsa-drugs` 不实现 Scheduled Source Discovery。药品 Source 更新是显式人工流程：

```text
operator provides a new XLSX
      ↓
snapshot + calculate SHA256
      ↓
inspect workbook + rights/provenance review
      ↓
compare SHA256 and declared Source Version
      ↓
same hash → exit
      ↓
new hash → full build + validate
      ↓
diff
      ↓
human review
      ↓
release
```

版本字符串相同但 SHA256 改变时也必须继续审查，不能因 `sourceVersion` unchanged 提前退出。确认是上游原地勘误后，为新构建分配新的 Build Revision，并保留旧 Release。

其他 Dataset 未来可以实现 Scheduled Update，但也必须先取得实际内容或使用可靠的条件请求，再比较 SHA256；ETag、Last-Modified 和页面版本号只能作为优化信号，不能代替内容身份。

早期统一采用：

> 自动构建 + 人工确认发布。

不要：

```text
官方网站更新
↓
无人审查
↓
直接覆盖 latest
```

---

# 59. Release Gate

正式 Release 前至少满足：

```text
source integrity verified
source provenance reviewed
workbook/layout fingerprint passed
schema validation passed
record count passed
null-rate passed
duplicate checks passed
diff reviewed
known lookup smoke tests passed
Chinese tokenizer behavior passed
JSON contract golden tests passed
SQLite integrity_check passed
no WAL/SHM/journal sidecars
compressed and uncompressed artifact hashes verified
Manifest schema and Registry entry validated
Distribution Gate: releaseEligible = true
Registry signature generated and verified
clean install/update/rollback smoke tests passed
```

当 Manifest 为 `releaseEligible: false` 时，构建仍可生成本地 validation artifact；远程分发 Workflow 跳过 SQLite、Parquet 和逐条数据上传。

---

# 60. Consumer Integration：Synthea

Synthea 是一个典型消费者，但不是项目核心。

大致：

```text
Synthea
  │
  ├── SNOMED
  ├── RxNorm
  └── LOINC
       │
       ▼
  Mapping Layer
       │
       ▼
cn-health-data
       │
       ▼
Chinese Clinical Representation
```

例如：

```text
SNOMED → ICD-CN
RxNorm → Chinese Drug Concept
LOINC → zh-CN display
```

身份信息可以使用：

```text
population-cn
geography-cn
```

构建 synthetic Chinese patient。

---

# 61. Consumer Integration：Hospital Simulation

医疗仿真系统可以使用：

```text
cn-health-data
       ↓
Hospital Baseline Compiler
```

生成：

```text
hospital drug formulary
hospital diagnosis dictionary
hospital lab catalog
hospital procedure catalog
charge catalog
```

Reference Data 回答：

> 国家体系中有哪些标准对象。

Hospital Baseline 回答：

> 这个虚拟医院选择了哪些对象。

---

# 62. Consumer Integration：Agent

Agent 最简单的接入方式：

```text
Agent Harness
     │
     ▼
 shell exec
     │
     ▼
 cn-health
     │
     ▼
 SQLite
```

Agent 工具定义甚至可以简单到：

```text
search_drug(query)
      ↓
cn-health drug search query --json
```

不要求为每种 Harness 单独维护 SDK。

---

# 63. Consumer Integration：FHIR

未来可提供 Reference → FHIR Terminology Projection，例如：

```text
CodeSystem
ValueSet
ConceptMap
```

但注意：

> SQLite Canonical Dataset 不应该以 FHIR 为唯一内部模型。

FHIR 是一种互操作表达，不应强迫所有 Reference Data 先变成 FHIR 再被程序使用。

---

# 64. Mapping 是长期高价值资产

部分原始数据可能可以重新获得，但项目不能依赖这一假设；来源会被替换、下线，也可能受访问或权利限制。

但：

```text
SNOMED → ICD-CN
RxNorm → NHSA/NMPA
LOINC → local LIS
```

经过人工和机器共同维护的高质量 Mapping 更难复制。

因此 Mapping 应拥有独立：

```text
version
provenance
confidence
method
review_status
```

并建立专门测试。

---

# 65. 初始实施路线

## Phase 0：Repository Bootstrap

完成：

```text
repo
uv workspace
pnpm workspace
basic docs
Dataset Contract
Manifest schema
Registry schema
CLI JSON schema
Distribution Gate
CI
```

不要求 Rust。

---

# 66. Phase 1：LOINC

目标：

> 验证完整 Dataset Compiler。

流程：

```text
ZIP
↓
CSV
↓
join zh-CN
↓
normalize
↓
SQLite
↓
manifest
```

验收：

```text
可重复构建
可查询
manifest 完整
validation 通过
```

---

# 67. Phase 2：NHC ICD

验证：

```text
XLSX source adapter
```

最终：

```text
diagnosis.sqlite
```

加入：

```text
FTS
```

---

# 68. Phase 3：NHC Procedure

复用 ICD 基础设施。

这是非常重要的一次架构检验：

> 如果实现第二个 XLSX Dataset 需要复制大量代码，说明 Source Adapter / Pipeline 边界设计有问题。

---

# 69. Phase 4：NHSA Drugs

正式进入大体量 XLSX Dataset。输入固定为当前声明的分发快照 `总表`，不实现 PDF Compiler。

需要解决：

```text
explicit local Source Snapshot
39.5 MB XLSX streaming read
exact 26-column header fingerprint
269110-row baseline
external link disabled
field mapping for 总表
validation
version diff
trigram search index
SQLite size
compression
```

这是第一个真正证明项目基础设施价值的数据集。

---

# 70. Phase 5：CLI Prototype

在前三到四个 Dataset 稳定后实现：

```text
cn-health dataset install
cn-health dataset list
cn-health search
```

可以先使用 TypeScript。

---

# 71. Phase 6：Rust Runtime

CLI contract 稳定后：

```text
TS prototype
     ↓
Rust Runtime
```

实现：

```text
native binaries
zstd
SQLite
manifest
dataset manager
search
JSON
```

---

# 72. Phase 7：npm Distribution

最终：

```bash
npx cn-health
```

运行 native binary。

---

# 73. Phase 8：Extended Data

逐步增加：

```text
NMPA drugs
NHSA medical services
NRDL
departments
consumables
UDI
IVD
regional prices
DRG
DIP
```

每个新 Dataset 都必须遵守相同 Contract。

---

# 74. 第一版开发优先级

不要同时实现所有东西。

第一个 milestone 应只有：

```text
LOINC
NHC ICD
NHC Procedure
NHSA Drugs
```

达到：

```text
Source
  ↓
Compiler
  ↓
SQLite
  ↓
Manifest
  ↓
Distribution Gate
  ↓
Release
```

以后再增加消费者。

---

# 75. Definition of Done：一个 Dataset

Dataset 只有满足以下条件才能认为“完成”。

## Source

- 明确 Authority 及其原始制定/分发角色；
- 明确 Source Version、文件名、size 和 SHA256；
- 明确 Acquisition、来源 URL（如有）和 Source Retention；
- Source Snapshot 可再次取得，或如实标记不可完整复现；
- 来源条款证据和公开分发配置明确。

## Compiler

- Extractor；
- Normalizer；
- Validation；
- source/config/dependency input digest；
- canonical deterministic build；
- 不解析未声明文件或 external links。

## Artifact

- SQLite；
- Manifest；
- immutable Release ID；
- canonical、压缩和解压 artifact checksums；
- record count；
- validation 与 diff reports。

## QA

- schema checks；
- known-record tests；
- null-rate checks；
- uniqueness；
- diff；
- tokenizer/search behavior；
- JSON contract；
- clean install/update/rollback。

## Documentation

- 字段说明；
- 来源说明；
- 权利依据与允许发布范围；
- 构建方法。

---

# 76. Definition of Done：项目 v0.1

v0.1 推荐达到：

```text
3+ stable datasets
1 experimental complex dataset
```

例如：

```text
stable:
  loinc-zh-cn
  nhc-icd10-clinical
  nhc-procedure-clinical

experimental:
  nhsa-drugs
```

并且：

```bash
uv run cn-health-build build nhsa-drugs \
  --source "$DRUG_SOURCE"
```

可以按 expected SHA256 构建当前基线。`nhsa-drugs` 在只有一个 Source 版本、或尚未配置远程分发元数据时保持 experimental；Parser 跑通本身不改变稳定性等级。

---

# 77. v0.2

重点：

```text
Rust CLI
Dataset Install
Local Search
Signed Dataset Registry
Atomic Install/Rollback
GitHub Releases
```

公开 Registry 和 GitHub Releases 只列出各自 Manifest 标记为可分发的 Dataset；其余 Dataset 继续使用 local Candidate workflow。

用户可以：

```bash
cn-health dataset install nhc-icd10-clinical
cn-health diagnosis search 糖尿病
```

---

# 78. v0.3

重点：

```text
NHSA drugs stable
NMPA mapping
medical services
manual same-version source replacement workflow
automated source discovery for eligible non-drug datasets
release diff
```

---

# 79. 长期架构

未来可能形成：

```text
                     cn-health-data
                          │
              Canonical Dataset Registry
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
      cn-health         SDK/API        Analytics
         CLI
          │
 ┌────────┼───────────────┐
 ▼        ▼               ▼
Agent   Synthea        HIS/Simulator
```

云 API 可以存在。

但它只是：

> 同一份 Dataset 的另一种 Runtime。

不应成为数据基础设施的唯一访问方式。

---

# 80. 项目长期设计原则

## Principle 1

**Official source is input, not runtime dependency.**

消费者不应该运行时访问政府网站。

---

## Principle 2

**Build once, query many times.**

复杂计算发生在 Build Time。

Runtime 必须简单。

---

## Principle 3

**Local first.**

Reference Data 适合离线、本地、确定性查询。

---

## Principle 4

**Immutable releases.**

历史版本不覆盖。

---

## Principle 5

**Provenance is data.**

来源信息不是 README 附属说明，而是正式 Dataset Metadata。

---

## Principle 6

**Validation before automation.**

没有严格 Validation，就不要做无人值守自动发布。

---

## Principle 7

**Canonical data is consumer-independent.**

不要为某个 HIS 或 Synthea 修改 canonical truth。

转换应该发生在 Adapter 层。

---

## Principle 8

**Mappings are explicit.**

不使用模糊的“中文化”覆盖源代码。

应保留：

```text
source concept
target concept
mapping relation
```

---

## Principle 9

**Simple before generic.**

先让：

```text
LOINC
ICD
Procedure
Drug
```

真正跑通。

不要先构建复杂的 Universal Dataset Framework。

---

## Principle 10

**Performance by preprocessing.**

运行时性能的核心不是复杂服务架构，而是：

```text
pre-normalized data
proper SQLite schema
indexes
FTS
local execution
```

---

# 81. 第一轮实际开发任务

建议从下面开始。

## Repository

创建：

```text
README.md
LICENSE
DATA-NOTICE.md
pyproject.toml
.python-version
.gitignore
```

初始化：

```bash
uv init
```

建立：

```text
python/compiler
datasets
schemas
docs
```

---

## Manifest

首先完成：

```text
schemas/manifest.schema.json
schemas/registry.schema.json
schemas/cli-output.schema.json
```

因为所有 Dataset 后面都依赖它。

---

## 第一个 Dataset

建立：

```text
datasets/loinc-zh-cn/
```

实现：

```text
discover
download
snapshot
extract
normalize
validate
sqlite
manifest
```

---

## 第二个 Dataset

建立：

```text
datasets/nhc-icd10-clinical/
```

第一次真正验证：

> Pipeline 是否可复用。

---

## 第三个 Dataset

```text
nhc-procedure-clinical
```

尽量复用 XLSX infrastructure。

---

## 第四个 Dataset

最后进入：

```text
nhsa-drugs
```

建立 `NhsaDrugXlsxAdapter` 和 `datasets/nhsa-drugs/workbook.yaml`，显式读取指定 XLSX 的 `总表`。验收当前 SHA256、269,110 行、26 列表头、零重复代码、零公式，并复用已有 XLSX streaming infrastructure；不建立 PDF Compiler 或官网同步任务。

---

# 82. 推荐第一阶段不要建立的东西

暂时不要做：

```text
Cloudflare
D1
Workers
KV
MCP Server
FHIR Terminology Server
GraphQL
Web Dashboard
PostgreSQL
Kubernetes
microservices
```

这些以后都容易增加。

真正困难的部分是：

```text
高质量 canonical dataset
```

先把这个壁垒建立起来。

---

# 83. 项目的核心工程闭环

最终每一个 Dataset 都应该遵循：

```text
Discover
     ↓
Acquire
     ↓
Inspect
     ↓
Extract
     ↓
Normalize
     ↓
Validate
     ↓
Compare
     ↓
Compile
     ↓
Package
     ↓
Release
     ↓
Consume
     ↓
Feedback
     ↓
Improve Parser / Mapping / Validation
```

随着 Dataset 数量增加，真正复利增长的不是“抓取的数据量”，而是：

```text
Source Adapter Library
Canonical Schemas
Mapping Assets
Validation Rules
Version History
Runtime
Developer Ecosystem
```

这些才是 `cn-health-data` 长期最有价值的基础设施资产。

---

# 84. 最终项目边界总结

`cn-health-data` 负责：

```text
现实医疗 Reference Data
        ↓
机器可读
        ↓
标准化
        ↓
版本化
        ↓
可追溯
        ↓
快速本地访问
```

它不负责：

```text
真实患者
医院实时运营
诊疗决策
具体 HIS 业务状态
```

消费者可以基于它分别构建：

```text
Synthetic Patient World
Hospital World
Clinical Simulation
FHIR Projection
Agent Tools
Research Dataset
```

因此项目长期应保持：

> **Reference Data First、Local First、Immutable、Provenance-aware、Consumer-independent、Agent-friendly。**

这也是整个项目后续所有架构决策的判断基准。
