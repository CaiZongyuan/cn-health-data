# CN Health Data

[English](README.md) | [简体中文](README.zh-CN.md)

CN Health Data 是一套本地优先的中国医疗健康参考数据工具链，用于将来源明确、可供不同
消费者复用的数据编译成可版本化、可追溯、可检索的产物。项目由 Python 编译器、不可变的
Dataset Contract 与 Manifest、Rust 原生 CLI，以及轻量 npm 启动器组成。

仓库围绕不同消费者需要的中国健康数据组织，而不是围绕某一个模拟器组织。目前可以从
用户明确提供的来源快照构建药品分类与疾病分类数据，也包含完整 WS/T 886 检验术语、
面向成人健康模拟的检验运行时投影，以及通用的地理、姓名和人口 Dataset。Synthea 通过
版本化消费投影获得明确支持。项目不会
自行下载所谓“最新版”数据，不保存患者数据，也不是生产级临床业务系统。

> **数据与许可证：** MIT License 只覆盖项目自行创作的软件代码和原创文档。来源数据
> 继续适用其自身条款；本项目不拥有这些数据，也不会通过项目许可证重新授权这些数据。
> 详见[数据权利与许可证](#数据权利与许可证)。

## 当前状态

| Dataset | 当前实现 | 已验证构建 | 记录数 | 公众可获取性 |
|---|---|---:|---:|---|
| `nhsa-drugs` | 药品分类与代码工作簿 `总表`的导入、校验、打包与检索 | `2026-01-09.r4` | 269,110 | 公共 Registry；默认安装 |
| `nhc-icd10-clinical` | 疾病分类与代码国家临床版 2.0（2022）的导入、校验、打包与检索 | `2022.r4` | 37,294 | 公共 Registry；默认安装 |
| `geography-cn` | 行政区划、居民点与邮政区域的版本化编译 | `2026-08-29.r2` | 24,731 | 公共 Registry；默认安装 |
| `names-cn` | 中文姓氏与男女名字组件的安全静态解析 | `40.37.0.r2` | 530 | 公共 Registry；默认安装 |
| `population-cn` | 中国年龄/性别人口边际分布 | `WPP2024.r2` | 3,171 | 公共 Registry；默认安装 |
| `nhc-lab-tests` | 完整 WS/T 886—2026 术语及按附录校验的类别、标本和标度代码 | `2026.r1` | 399 | 公共 Registry；默认安装 |
| `laboratory-cn` | 带成人 reference、健康模拟元数据和医院 panel 的 WS/T 886 运行时投影 | `2026-09-01.r1` | 84 项、96 条 reference、15 个 panel | 公共 Registry；默认安装 |
| `loinc-zh-cn` | 完整 LOINC 2.83 核心表、官方中文变体、UCUM 候选单位、SYSTEM Part 与 panel | `2.83.r2` | 365,722 | 公共 Registry；默认安装 |
| `nhc-procedure-clinical` | 已定义 Contract 与 Schema，编译器暂缓实现 | 暂无 | 暂无 | 未实现 |

表中的构建标识来自当前开发环境中已经验证的 Candidate。本仓库分发编译器、运行时、
合成测试 Fixture，以及八个已实现 Dataset 的规范化公共 Release。`tmp/`、`.work/` 和
`dist/` 均被 Git 忽略，因此克隆仓库不会附带私有来源文件、构建缓存或历史 Candidate；
最新压缩 SQLite、Parquet、Manifest 和报告位于 `distribution/`。

当前已经实现的基础设施包括：

- XLSX 流式提取、规范化、校验与来源指纹检查；
- 确定性 SQLite 产物，以及 FTS5 trigram 和双字 bigram 中文搜索；
- Parquet、zstd 压缩 SQLite、校验报告、Diff 和 Manifest；
- 不可变 Release 修订，以及与上一 Release 的差异比较；
- 本地安装时校验压缩前后 SHA256、限制解压大小，并执行 SQLite 完整性检查；
- 已安装版本的查看、切换与回退；
- 药品、疾病、LOINC、WS/T 886 检验项目和 panel 的精确查询与文本搜索命令；
- 完整 LOINC 2.83 编译，包含 112,405 个核心概念和 96,518 个官方中文显示；
- 84 个成人 simulation-ready 检验项目、96 条带 provenance 的 reference 和 15 个项目 panel；
- 中国合成姓名、地址、`100` 电话和 `990000` 模拟居民号码的确定性生成；
- 固定 Synthea commit 的 profile 投影、FHIR R4 身份本地化和内部 HTTP 服务；
- Ed25519 签名完整公共 Registry、默认全量 `init`、选择性 `--only` 和离线 `doctor`；
- 四个平台原生包的 tag 构建，以及只负责调用原生二进制文件的 npm 启动器。

准确的已实现边界见
[`docs/implementation-status.md`](docs/implementation-status.md)。

## 架构

```text
声明的来源文件
      |
      v
快照 -> 检查 -> 提取 -> 规范化 -> 校验 -> Diff
                                      |
                                      v
                  Manifest <- 打包 <- SQLite + Parquet
                       |
                       v
                 分发策略 -> Release/Registry
                                       |
                                       v
                                Rust 本地运行时
```

Python 负责构建阶段的来源处理和产物编译；SQLite 是规范的运行时产物。Rust CLI 将
所有本地 Candidate 和远程下载都视为不可信输入，完成验证后安装到版本化目录，并以
原子方式切换当前版本指针。npm 仅作为启动器，不会再次实现查询逻辑。

每个 Dataset 都由 `datasets/<dataset-id>/` 下的 Contract 管理：

- `dataset.yaml` 声明身份、权威来源、来源哈希、版本策略、校验规则、运行时要求和
  权利状态；
- `workbook.yaml` 或 `layout.yaml` 在需要时记录来源结构指纹；
- `schema.sql` 定义运行时数据库及搜索索引。

完整设计和约束见 [`docs/architecture.md`](docs/architecture.md) 与
[`docs/implementation-handbook.md`](docs/implementation-handbook.md)。

## 仓库目录

```text
datasets/          Dataset Contract、来源指纹和 SQLite Schema
docs/              架构、实现、来源与数据权利文档
mappings/          独立版本化的术语映射占位目录
npm/               原生 CLI 的轻量启动器
python/compiler/   Python 编译器、来源适配器和测试
rust/cn-health/    原生安装与查询运行时
schemas/           Contract、Manifest、Registry 和 CLI 输出的 JSON Schema
distribution/      签名公共 Registry 与八个最新规范化 Dataset
tmp/               本地原始输入，Git 忽略
.work/             来源快照与本地工作数据，Git 忽略
dist/              不可变的本地 Candidate，Git 忽略
```

## 环境要求

普通用户可以选择 npm 或原生发行包：

| 安装方式 | 运行要求 | 支持平台 |
|---|---|---|
| npm `cn-health@0.5.3` | Node.js 22 或更高版本 | Linux x64、macOS x64/arm64、Windows x64 |
| GitHub 原生归档 | 无额外语言运行时 | Linux x64、macOS x64/arm64、Windows x64 |

两种方式运行的是同一个 Rust CLI。npm 包只是平台二进制解析器，不包含第二套查询逻辑。
普通用户不需要安装 Python、Rust、`uv`、pnpm，也不需要准备任何来源工作簿。

源码开发环境需要：

- Git；
- Python 3.12；
- [`uv`](https://docs.astral.sh/uv/)；
- Rust 1.96，用于构建原生运行时；
- Node.js 22 和 pnpm 11，仅在开发 npm 启动器时需要。

构建真实数据集还需要 Dataset Contract 中声明的精确来源文件。单元测试与集成测试
使用合成 Fixture，不依赖第三方 XLSX 文件。

## 快速开始

### 使用 npm 安装

这是最简单的跨平台安装方式：

```bash
npm install --global cn-health@0.5.3
cn-health --version
```

版本命令应输出：

```text
cn-health 0.5.3
```

npm 会根据当前操作系统只安装一个可选平台包。例如 Linux x64 安装
`@cn-health/cli-linux-x64`；其他平台包显示为未满足的 optional dependency 是正常行为。

临时试用也可以使用 `npx --yes cn-health@0.5.3 --version`，但日常查询建议全局安装，避免
每次重新解析包。

### 使用原生发行包

不希望安装 Node.js 时，可从
[`v0.5.3` GitHub Release](https://github.com/CaiZongyuan/cn-health-data/releases/tag/v0.5.3)
下载对应归档：

| 系统 | Release 资产 |
|---|---|
| Linux x64 | `cn-health-v0.5.3-linux-x64.tar.gz` |
| macOS Intel | `cn-health-v0.5.3-darwin-x64.tar.gz` |
| macOS Apple Silicon | `cn-health-v0.5.3-darwin-arm64.tar.gz` |
| Windows x64 | `cn-health-v0.5.3-win32-x64.tar.gz` |

Linux/macOS 解压并直接运行：

```bash
tar -xzf cn-health-v0.5.3-linux-x64.tar.gz
./cn-health-v0.5.3-linux-x64/cn-health --version
```

Windows PowerShell 可以使用系统自带的 `tar`：

```powershell
tar -xzf cn-health-v0.5.3-win32-x64.tar.gz
.\cn-health-v0.5.3-win32-x64\cn-health.exe --version
```

每个原生归档同时包含 `LICENSE` 和 `DATA-NOTICE.md`。macOS 产物目前未做 Apple
notarization；运行方式受本机 Gatekeeper 和组织安全策略约束。

### 初始化完整数据

安装 CLI 后执行：

```bash
cn-health init --json
```

首次运行会从内置 HTTPS Registry 下载、验证并安装八个已实现 Dataset。当前压缩下载约
75.40MiB，解压后的 SQLite 合计约 784.50MiB。成功输出包含以下 Release：

```json
{"command":"init","items":[{"datasetId":"geography-cn","releaseId":"geography-cn@2026-08-29.r2","status":"installed"},{"datasetId":"laboratory-cn","releaseId":"laboratory-cn@2026-09-01.r1","status":"installed"},{"datasetId":"loinc-zh-cn","releaseId":"loinc-zh-cn@2.83.r2","status":"installed"},{"datasetId":"names-cn","releaseId":"names-cn@40.37.0.r2","status":"installed"},{"datasetId":"nhc-icd10-clinical","releaseId":"nhc-icd10-clinical@2022.r4","status":"installed"},{"datasetId":"nhc-lab-tests","releaseId":"nhc-lab-tests@2026.r1","status":"installed"},{"datasetId":"nhsa-drugs","releaseId":"nhsa-drugs@2026-01-09.r4","status":"installed"},{"datasetId":"population-cn","releaseId":"population-cn@WPP2024.r2","status":"installed"}],"schemaVersion":2,"selection":"all"}
```

`init` 是幂等命令；同一 Release 已存在时状态为 `already-installed`。只安装指定数据时：

```bash
cn-health init --only nhsa-drugs,nhc-icd10-clinical
```

未知 Dataset ID 会在网络访问前失败。每个 Dataset 的安装路径都会校验：

- Registry Ed25519 签名和固定公钥 key ID；
- Manifest 摘要、Dataset/Release 身份和撤回状态；
- `releaseEligible` 分发资格与同源 HTTPS URL；
- zstd 传输文件和解压后 SQLite 的 SHA256 与大小；
- 解压大小上限、SQLite `integrity_check` 和 application ID；
- Manifest 声明的最低 CLI 版本。

> 公共分发只包含规范化产物，不包含 `tmp/` 中的原始 XLSX、ZIP、PDF 或来源快照。
> `nhc-procedure-clinical` 尚未实现编译器，因此不在默认八 Dataset 中。

### 查询和精确读取

按中文文本搜索：

```bash
cn-health laboratory search 白细胞 --limit 10 --json
cn-health drug search 二甲双胍 --limit 10 --json
cn-health diagnosis search 糖尿病 --limit 10 --json
cn-health loinc search 葡萄糖 --limit 10 --json
```

按 WS/T 886 code 精确读取或展开医院 panel：

```bash
cn-health laboratory get 0100101A --json
cn-health laboratory panel search 血常规 --json
cn-health laboratory panel get CN-LAB-CBC-5DIFF --json
```

`0100101A` 返回白细胞计数的分类、标本、标度、单位、precision、成人 reference
provenance 和显式健康模拟范围。Panel get 按稳定顺序返回带完整元数据的成员。搜索词至少
需要两个 Unicode 字符；默认上限为 20，`--limit`
允许 1 到 200。`--json` 输出包含稳定的 `schemaVersion`、Dataset/Release 身份、查询参数、
结果和分页元数据。

### 检查安装状态

```bash
cn-health doctor
cn-health dataset list --json
cn-health dataset info laboratory-cn --json
cn-health dataset versions laboratory-cn --json
```

`doctor` 检查八个默认 Dataset 是否已安装、是否来自签名 Registry，并对药品、诊断、
LOINC 和检验执行代表性精确读取。`doctor --json` 还会显示实际 `dataDir` 和编译进 CLI
的默认 Registry URL。

### Materialize 精确 Release

构建和 CI consumer 可以请求一个精确的签名 Release，而不读取 runtime 的私有数据目录：

```bash
cn-health dataset materialize laboratory-cn laboratory-cn@2026-09-01.r1 \
  --registry https://raw.githubusercontent.com/CaiZongyuan/cn-health-data/main/distribution/registry.json \
  --public-key ./distribution/registry.pub \
  --output ./staging/laboratory-cn \
  --json
```

输出目录必须不存在或为空。成功时原子发布原始 `manifest.json`、已验证的 `data.sqlite`
和 `materialization.json`。JSON 结果固定 CLI、Dataset/Release/Schema、Registry key ID 和
信任状态、Manifest hash 及 SQLite hash/大小。相同 Release 已安装时仍重新验证 Registry
和 Manifest，但复用已验证的本地 SQLite。失败不会留下可消费输出，也不会覆盖非空目标。

### 数据目录和离线运行

未指定 `--data-dir` 时，CLI 使用操作系统为 `org.cn-health.cn-health` 分配的应用数据目录。
不要猜测该路径；使用以下命令查看：

```bash
cn-health doctor --json
```

需要隔离测试、CI 或多个运行环境时，将全局参数放在子命令之前：

```bash
cn-health --data-dir /absolute/path/to/cn-health-data init
cn-health --data-dir /absolute/path/to/cn-health-data laboratory search 血糖 --json
```

`init` 需要网络访问公共 Registry；安装完成后，查询、精确读取、Dataset 信息和 `doctor`
均不访问网络。卸载 npm 包不会自动删除应用数据目录。

### 升级

npm 用户升级 CLI 后重新执行幂等初始化，以采用 Registry 当前推荐且未撤回的 Release：

```bash
npm install --global cn-health@latest
cn-health --version
cn-health init
cn-health doctor
```

原生包用户从 GitHub Releases 下载新版本并替换自己的可执行文件。旧 Dataset Release
仍保留在数据目录中；`dataset use` 可以在已安装版本之间切换。

### 常见问题

- `No cn-health binary for ...`：当前平台不受支持，或安装时省略了 optional dependency。
  使用 Node.js 22+，并以 `npm install --global cn-health@latest --include=optional` 重新安装。
- `EACCES`：`0.2.0` 的 npm 平台包没有保留 Unix 执行位；升级到 `0.2.1` 或更高版本。
- `DATASET_NOT_INSTALLED`：先运行 `cn-health init`，并确认查询使用了相同的 `--data-dir`。
- `CLI_VERSION_INCOMPATIBLE`：Manifest 需要更新的运行时；先升级 `cn-health`，再重新初始化。
- `search query must contain at least two Unicode characters`：搜索词太短；使用至少两个字符，
  或在已知 code 时改用 `get`。
- Registry/HTTPS 下载错误：初始化需要访问 GitHub Raw 内容；检查代理、DNS、TLS 和组织
  网络策略。不要通过关闭签名或哈希校验绕过错误。

### 贡献者快速开始

贡献者 clone 仓库后使用一条命令建立开发环境并完成同一条真实查询：

```bash
scripts/bootstrap-dev.sh
```

## 来源数据

来源获取采用显式、本地模式。编译器不会扫描 `tmp/`，不会按修改时间选择文件，也不会
从上游 PDF 或网站进行同步。每次构建都必须传入精确的来源路径。

当前声明的第三方来源输入如下：

| Dataset | 输入约束 | 工作表 | 预期 SHA256 |
|---|---|---|---|
| `nhsa-drugs` | 由 `DRUG_SOURCE` 指定的药品分类与代码工作簿 | `总表` | `9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67` |
| `nhc-icd10-clinical` | 由 `DIAGNOSIS_SOURCE` 指定的疾病分类国家临床版工作簿 | `2.0（2022版）` | `e927d8ec0d25a64125e24b26dcc3987b0021b5d8b94c0f4d7ae7e05f1592af52` |
| `nhc-lab-tests` | 显式指定的 WS/T 886—2026 Markdown 转换件 | 表 1 与附录 A | `a7f5e038dba32730a61437297c918c073b347304dc09ed6f6844025b2137bb8c` |
| `laboratory-cn` panel 证据 | 检验类医疗服务价格项目立项指南映射关系表 | `映射关系表（试行）` | `4625a6f73e2eab2f76a47434b4aabfa7bb9b9328ac2462d36c1bd97c6e7de861` |

药品编译器只读取声明的工作簿 `总表`。`tmp/` 中下载的药品 PDF 不参与构建。手术操作
工作簿也不会被读取，因为手术分类开发已经暂缓。

`nhc-lab-tests` 编译 WS/T 886 全部 399 条记录，并依据附录 A 校验代码中的类别、标本和
标度。`laboratory-cn` 从同一显式来源 hydrate 术语，再应用项目维护的
[`runtime.csv`](datasets/laboratory-cn/runtime.csv) 与
[`panels.csv`](datasets/laboratory-cn/panels.csv)。价格映射工作簿只作为 panel 证据，
其中的收费代码和方法学代码不表示为 WS/T 886 或 LOINC 官方映射。

`loinc-zh-cn` 使用经账户下载、由运维方显式提供的官方
`tmp/Loinc_2.83.zip`。同一个包包含完整核心表、中文 `zhCN5` Linguistic Variant、Part、
panel 和 LOINC License 5.8。原始包保持私有并被 Git 忽略；精确 hash、成员布局、数量、
署名和 rights 决策固定在 [`datasets/loinc-zh-cn/`](datasets/loinc-zh-cn/) 下。

构建前可以检查输入文件：

```bash
export DRUG_SOURCE=/absolute/path/to/drug-classification.xlsx
export DIAGNOSIS_SOURCE=/absolute/path/to/clinical-diagnosis-2022.xlsx
sha256sum \
  "$DRUG_SOURCE" \
  "$DIAGNOSIS_SOURCE"
```

构建期间，编译器会校验声明的 SHA256、文件大小、工作表、表头、XLSX 容器指纹和公式
预期。匹配的输入会复制到 `.work/sources/<sha256>/source.xlsx`，形成本地的内容寻址
快照。原文件和快照均由 Git 忽略，编译器也不会将它们打包为 Release 产物。

Candidate 的 Provenance 会记录当前 Git 提交以及编译器输入，因此正常 CLI 构建会拒绝
存在未提交改动的 Git 工作区。

## 构建本地 Candidate

以下示例假定 `dist/` 为空，并创建 revision 1：

```bash
uv run cn-health-build build nhsa-drugs \
  --source "$DRUG_SOURCE" \
  --build-revision 1 \
  --sequence 1

uv run cn-health-build build nhc-icd10-clinical \
  --source "$DIAGNOSIS_SOURCE" \
  --build-revision 1 \
  --sequence 1

uv run cn-health-build build laboratory-cn \
  --source 'tmp/WST_886—2026.md' \
  --panel-source 'tmp/检验类医疗服务价格项目立项指南映射关系表.xlsx' \
  --build-revision 1 \
  --sequence 3

uv run cn-health-build build nhc-lab-tests \
  --source 'tmp/WST_886—2026.md' \
  --build-revision 1 \
  --sequence 1

uv run cn-health-build build loinc-zh-cn \
  --source tmp/Loinc_2.83.zip \
  --build-revision 1 \
  --sequence 1
```

编译器会输出 Release 目录和 Manifest 路径。每个 Candidate 的结构如下：

```text
dist/<dataset-id>/releases/<source-version>.r<revision>/
├── data.sqlite
├── data.sqlite.zst
├── data.parquet
├── diff.json
├── manifest.json
└── validation.json
```

Candidate 目录不可变，构建器拒绝覆盖已经存在的目录。当来源版本不变、但编译器或元数据
需要修正时，应使用新的 Build Revision：

```bash
uv run cn-health-build build nhc-icd10-clinical \
  --source 'tmp/疾病分类与代码国家临床版2.0(2022汇总版).xlsx' \
  --build-revision 2 \
  --sequence 2 \
  --base-release dist/nhc-icd10-clinical/releases/2022.r1
```

该命令生成 `nhc-icd10-clinical@2022.r2`，将 `2022.r1` 记录为前序版本，并根据基础
SQLite 生成 `diff.json`。Source Version、Build Revision、Release Sequence、Compiler
Version、Dataset Schema Version 与 Manifest Schema Version 是相互独立的版本维度。

## 通用中国数据与 Synthea 支持

`geography-cn`、`names-cn` 和 `population-cn` 是通用 Dataset；Synthea profile 是消费这些
Release 的版本化投影，不是 canonical 数据模型，也不代表整个仓库的发布优先级。

当前实现复用固定版本的上游参考材料，Dataset Contract、校验、规范化和 Release 构建仍由
本仓库负责：

| Dataset | 固定的参考材料 | 实现选择 |
|---|---|---|
| `geography-cn` | AreaCity 行政区划，加 GeoNames 中国居民点与邮政数据 | 编译为保留各来源 Provenance 的组合 Candidate，运行时不依赖这些参考项目 |
| `names-cn` | Faker `zh_CN` person provider 40.37.0 | 只用 Python AST 读取声明的字面量，不导入或执行来源模块 |
| `population-cn` | 联合国《世界人口展望 2024》Medium projection | 只保留中国聚合年龄/性别边际分布，不构造缺乏统计依据的联合分布 |

当前已验证的 Synthea 组合为：

```text
geography-cn@2026-08-29.r1
names-cn@40.37.0.r1
population-cn@WPP2024.r1
synthea-cn@2026-08-29.r3
Synthea d9d07a6eef91ee5144293b42ab64224d84d124f8
```

已验证 profile 可从
[`distribution/profiles/synthea-cn/2026-08-29.r3/`](distribution/profiles/synthea-cn/2026-08-29.r3/manifest.json)
直接获取。它仍固定使用 Manifest 中记录的 r1 依赖哈希；canonical Dataset 当前推荐的 r2
只是分发元数据 revision，不改变这份 profile 的已验证依赖身份。

从三个 Candidate 构建 profile：

```bash
uv run cn-health-build synthea profile \
  --geography-release dist/geography-cn/releases/2026-08-29.r1 \
  --names-release dist/names-cn/releases/40.37.0.r1 \
  --population-release dist/population-cn/releases/WPP2024.r1 \
  --output-root dist/synthea-cn-profile/releases \
  --profile-version 2026-08-29 \
  --build-revision 3 \
  --reference-year 2026 \
  --synthea-commit d9d07a6eef91ee5144293b42ab64224d84d124f8
```

本地化一个自包含 Synthea FHIR R4 collection Bundle：

```bash
uv run cn-health-build synthea localize \
  --input /path/to/raw-bundle.json \
  --output .work/localized-bundle.json \
  --profile dist/synthea-cn-profile/releases/2026-08-29.r3 \
  --geography-release dist/geography-cn/releases/2026-08-29.r1 \
  --names-release dist/names-cn/releases/40.37.0.r1 \
  --population-release dist/population-cn/releases/WPP2024.r1 \
  --seed patient-1
```

长驻消费者可以构建非 root localizer 镜像，或直接启动内部服务。服务启动时一次验证
profile 内容哈希、文件和三个 Candidate，之后每个响应返回相同 provenance：

```bash
docker build -f Dockerfile.synthea-localizer -t cn-health-synthea-localizer .

CN_HEALTH_SYNTHEA_PROFILE_PATH="$PWD/dist/synthea-cn-profile/releases/2026-08-29.r3" \
CN_HEALTH_GEOGRAPHY_RELEASE_PATH="$PWD/dist/geography-cn/releases/2026-08-29.r1" \
CN_HEALTH_NAMES_RELEASE_PATH="$PWD/dist/names-cn/releases/40.37.0.r1" \
CN_HEALTH_POPULATION_RELEASE_PATH="$PWD/dist/population-cn/releases/WPP2024.r1" \
uv run cn-health-synthea-service --host 127.0.0.1
```

本地化器只替换 Patient、Practitioner 和 Organization 的身份展示，保留临床资源 ID、
编码、日期、数值、单位与引用闭包。完整合同与 Docker 验收见
[`docs/synthea-cn-spec.md`](docs/synthea-cn-spec.md)。

在身份本地化后，可以应用固定 Synthea commit 的临床中文显示目录：

```bash
uv run cn-health-build synthea translation project \
  --input .work/localized-bundle.json \
  --catalog translations/synthea-zh-cn/catalog.jsonl \
  --output .work/localized-bundle.zh-CN.json \
  --report .work/localized-bundle.zh-CN.report.json \
  --release-id synthea-zh-cn@2026-08-30.r1 \
  --allow-machine-draft
```

当前目录覆盖固定版本全部 242 个 module：2,149 个 module 术语和 27 个 exporter 补充
术语均无缺口。18 条项目精选 LOINC 显示为 `approved`，其余 2,158 条已经第二个 Agent
复核并标记为 `machine-checked`。原有 51 条复核标志均已完成证据复核并解决，其中 18 条
确认是 Synthea module 上下文或选码问题，中文显示继续忠实表达实际编码。实验开关必须
显式提供，严格模式只采用 `approved` 记录。构建和运行时均不调用翻译 API。机器可读
结果见
[`translations/synthea-zh-cn/coverage.json`](translations/synthea-zh-cn/coverage.json)。

## 成人检验运行时

`nhc-lab-tests@2026.r1` 包含 WS/T 886—2026 全部 399 条术语。
`laboratory-cn@2026-09-01.r1` 将其中 84 个常用成人项目投影为 96 条 reference 和 15 个
医院 panel。定量项目提供单位、precision 和显式 uniform 模拟范围；定性/定序项目提供
固定健康正常值。每条 reference 都区分国家标准与项目整理 provenance。

LOINC 现在是可选 crosswalk，不是主身份。独立的 `loinc-zh-cn@2.83.r2` Release 包含
112,405 个核心概念和 96,518 条官方中文翻译。不可变的 schema v1 laboratory Release
仍可下载，并可由 CLI v0.4.0 读取。详见
[`datasets/laboratory-cn/README.md`](datasets/laboratory-cn/README.md)。

## 本地 Candidate 安装与查询

先构建运行时，再通过本地 Manifest 安装 Candidate。显式指定数据目录可以让示例保持
隔离且容易清理：

```bash
cargo build -p cn-health

target/debug/cn-health --data-dir .work/runtime dataset install \
  --local-manifest dist/nhsa-drugs/releases/2026-01-09.r1/manifest.json

target/debug/cn-health --data-dir .work/runtime dataset install \
  --local-manifest dist/nhc-icd10-clinical/releases/2022.r1/manifest.json
```

本地安装会校验压缩产物的哈希和大小，在 Manifest 声明的大小上限内解压，校验未压缩
文件的哈希和大小，并执行 SQLite `integrity_check` 与 application ID 检查。本地
Candidate 的信任状态显示为 `local-untrusted`，用于和通过签名 Registry 验证的
Release 区分。

可以按中文文本搜索，也可以按代码精确查询：

```bash
target/debug/cn-health --data-dir .work/runtime drug search 二甲双胍 --limit 10 --json
target/debug/cn-health --data-dir .work/runtime drug get XA10BAE021A010010201650 --json

target/debug/cn-health --data-dir .work/runtime diagnosis search 糖尿病 --limit 10 --json
target/debug/cn-health --data-dir .work/runtime diagnosis get E14.900x001 --json
```

搜索词至少需要两个 Unicode 字符。默认返回上限为 20，可接受范围是 1 到 200。
`--json` 搜索结果使用稳定信封结构，包含 `schemaVersion`、命令与 Dataset 身份、查询
参数、按相关度排序的 `items` 和分页元数据。精确 `get` 始终输出单个 JSON 对象。

查看已安装数据并切换当前版本：

```bash
target/debug/cn-health --data-dir .work/runtime dataset list --json
target/debug/cn-health --data-dir .work/runtime dataset info nhsa-drugs --json
target/debug/cn-health --data-dir .work/runtime dataset versions nhsa-drugs --json
target/debug/cn-health --data-dir .work/runtime dataset use \
  nhsa-drugs nhsa-drugs@2026-01-09.r1
```

安装新 revision 时，旧版本会继续保留，新安装的版本成为当前版本。`dataset use` 只会
原子切换 current pointer，因此回退不会修改任一已安装 Release。

未指定 `--data-dir` 时，CLI 使用操作系统为 `org.cn-health.cn-health` 项目标识分配的
应用数据目录。

## 签名 Registry 与远程安装

仓库提供一个由 CLI 固定公钥验证的完整公共 Registry，包含八个已实现 Dataset 的当前
推荐 Release。公共 Manifest 只声明实际托管的 zstd、Parquet、报告和许可证文件；未压缩
SQLite 由客户端从 zstd 有界解压并按 Manifest 回验。

当运维方已经根据相应来源条款和预期用途准备好分发元数据后，可以生成 Ed25519 原始
密钥并构建签名 Registry。以下示例将开发密钥和产物放在 Git 忽略的 `.work/` 目录中；
请替换大写的路径占位符：

```bash
uv run cn-health-build registry keygen \
  --private-key .work/registry/registry.key \
  --public-key .work/registry/registry.pub

uv run cn-health-build registry build \
  dist/DATASET_ID/releases/RELEASE/manifest.json \
  --manifest-base-url https://data.example/releases \
  --private-key .work/registry/registry.key \
  --output .work/registry/registry.json \
  --signature .work/registry/registry.json.sig
```

生产私钥必须保存在仓库检出目录和公开托管服务器之外。Registry、分离签名、Manifest
与压缩产物应按声明的同源 HTTPS URL 发布。`cn-health init` 使用内置地址与公钥。操作方
也可以显式指定其他 Registry，安装其中推荐且未撤销的 Release：

```bash
target/debug/cn-health --data-dir .work/runtime dataset install DATASET_ID \
  --registry https://data.example/registry.json \
  --public-key .work/registry/registry.pub
```

运行时会验证 Registry 签名和 key ID、Manifest 摘要和身份、发布资格、产物哈希与
大小，以及同源 URL 规则。普通 HTTP 只允许用于 loopback 开发地址。

远程 GET 使用 10 秒连接超时；传输错误或 HTTP 408/429/500/502/503/504 最多共尝试
四次，并采用带 Full Jitter 的有上限指数退避，`Retry-After` 最长遵守 30 秒。重试进度
只写 stderr。JSON 命令耗尽重试后返回 `REMOTE_UNAVAILABLE`、`retryable: true` 和尝试
次数，并以状态码 7 退出；签名、哈希、Schema、撤销、权限和本地 I/O 错误绝不重试。

## npm 启动器

公开包 [`cn-health`](https://www.npmjs.com/package/cn-health) 是轻量 JavaScript 启动器。
它只向原生 CLI 转发参数、标准输入输出、信号和退出码，不包含数据或查询逻辑。平台包为：

- `@cn-health/cli-linux-x64`；
- `@cn-health/cli-darwin-x64`；
- `@cn-health/cli-darwin-arm64`；
- `@cn-health/cli-win32-x64`。

启动器按以下顺序解析二进制：

1. 开发者显式设置的 `CN_HEALTH_BINARY`；
2. 与当前 `process.platform/process.arch` 匹配的 optional platform package；
3. 源码仓库内的 `target/release/cn-health` 开发构建。

找不到实际文件时会明确报错，不会下载未经验证的可执行文件，也不会回退到 JavaScript
实现。`0.2.0` 的 Unix 平台包缺少执行位，已经由 `0.2.1` 及后续版本替代。

本地开发时，将它指向已经构建的二进制文件：

```bash
pnpm install --frozen-lockfile
cargo build --release -p cn-health

CN_HEALTH_BINARY="$PWD/target/release/cn-health" \
  node npm/cn-health/bin/cn-health.js \
  --data-dir .work/runtime dataset list --json
```

tag 发行工作流为 Linux x64、macOS x64/arm64 和 Windows x64 构建原生归档及 npm
平台包，先发布平台包，再发布依赖它们的 launcher。发布脚本会跳过 npm 中已经存在的
相同版本，因此中断后可以从 GitHub Release 的 `.tgz` 资产安全恢复。

## 开发与测试

运行完整的本地检查。Python 和 Rust 命令与仓库 CI 对齐，最后一条命令单独覆盖 npm
启动器：

```bash
uv sync --locked
uv run ruff check .
uv run mypy python/compiler/src
uv run pytest

cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace

pnpm --filter cn-health test
```

Dataset 解析器和构建测试使用已提交的合成 Fixture；当 Git 忽略的固定输入存在时，可选
本地测试还会验证真实来源的条数和哈希，但不会把原始记录提交为测试 Fixture。修改来源
适配器时，应同步更新 Contract、结构指纹、校验基线、Provenance、分发信息与测试。
贡献规则见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

## 数据权利与许可证

除具体文件另有声明外，项目自行创作的软件代码和原创文档采用
[MIT License](LICENSE)。

MIT **不会**自动覆盖：

- 第三方原始或镜像来源文件；
- 从第三方来源规范化生成的逐条数据；
- 生成的 SQLite、Parquet、Mapping 或类似数据产物；
- 第三方名称、标识及其他受保护材料。

第三方数据继续适用其来源条款；仓库的 MIT License 不会改变这些条款，也不会额外授予
数据使用或分发权限。Dataset Contract 和 Release Manifest 提供了记录 Provenance、
署名与分发信息的字段。分发数据产物的一方应自行确认并遵守适用于相应来源的条款。

获取、分享或发布任何数据集之前，请先阅读 [`DATA-NOTICE.md`](DATA-NOTICE.md) 和
[`docs/data-rights.md`](docs/data-rights.md)。

## 范围与已知限制

- 本项目提供参考数据工具，不构成医疗建议，也不是生产级临床决策系统。
- 项目只处理参考数据，不处理或保存真实患者数据。
- 药品分类使用声明的工作簿 `总表`，未实现 PDF 同步链路。
- 即使本地存在工作簿，手术操作分类仍按当前计划暂缓开发。
- `laboratory-cn` 提供成人健康模拟元数据，不做患者级或疾病驱动的检验模型。
- 公共 Registry 分发八个最新规范化 Dataset；来源身份、版本、哈希、署名和适用声明
  保留在各自 Manifest 中，原始来源文件不公开。
- `synthea-zh-cn` 已覆盖固定 Synthea 版本，51 条歧义均有证据 resolution，但 2,158 条
  仍是机器复核而非临床专家批准，不能表示为官方术语语言包。

## 文档索引

- [`docs/full-distribution-spec.md`](docs/full-distribution-spec.md)：完整公共分发与运行时契约
- [`docs/publication-decision.md`](docs/publication-decision.md)：规范化产物发布决定与署名条件
- [`docs/implementation-status.md`](docs/implementation-status.md)：实现边界与待完成项
- [`docs/implementation-handbook.md`](docs/implementation-handbook.md)：规范性实施手册
- [`docs/synthea-cn-spec.md`](docs/synthea-cn-spec.md)：中国人口数据、Synthea 投影与消费者
  接入的可执行规格
- [`docs/loinc-zh-cn-spec.md`](docs/loinc-zh-cn-spec.md)：完整官方 LOINC 简体中文
  Candidate 的来源、模型、构建与验收规格
- [`docs/synthea-zh-localization-plan.md`](docs/synthea-zh-localization-plan.md)：Synthea
  临床内容中文显示、API 分批翻译与验收计划
- [`docs/architecture.md`](docs/architecture.md)：组件架构概览
- [`docs/dataset-format.md`](docs/dataset-format.md)：Dataset Contract 结构
- [`docs/source-inventory.md`](docs/source-inventory.md)：数据来源清单与状态
- [`docs/data-rights.md`](docs/data-rights.md)：数据来源、许可证范围与分发元数据
- [`DATA-NOTICE.md`](DATA-NOTICE.md)：中英双语的数据权属与许可证声明
