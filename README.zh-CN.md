# CN Health Data

[English](README.md) | [简体中文](README.zh-CN.md)

CN Health Data 是一套本地优先的中国医疗健康参考数据工具链，用于将来源明确、可供不同
消费者复用的数据编译成可版本化、可追溯、可检索的产物。项目由 Python 编译器、不可变的
Dataset Contract 与 Manifest、Rust 原生 CLI，以及轻量 npm 启动器组成。

仓库围绕不同消费者需要的中国健康数据组织，而不是围绕某一个模拟器组织。目前可以从
用户明确提供的 XLSX 快照构建药品分类与疾病分类数据，也包含项目自行编写的精选检验目录，
以及通用的地理、姓名和人口 Dataset。Synthea 通过版本化消费投影获得明确支持。项目不会
自行下载所谓“最新版”数据，不保存患者数据，也不是生产级临床业务系统。

> **数据与许可证：** MIT License 只覆盖项目自行创作的软件代码和原创文档。来源数据
> 继续适用其自身条款；本项目不拥有这些数据，也不会通过项目许可证重新授权这些数据。
> 详见[数据权利与许可证](#数据权利与许可证)。

## 当前状态

| Dataset | 当前实现 | 已验证的本地构建 | 记录数 |
|---|---|---:|---:|
| `nhsa-drugs` | 药品分类与代码工作簿 `总表`的导入、校验、打包与检索 | `2026-01-09.r3` | 269,110 |
| `nhc-icd10-clinical` | 疾病分类与代码国家临床版 2.0（2022）的导入、校验、打包与检索 | `2022.r3` | 37,294 |
| `geography-cn` | 行政区划、居民点与邮政区域的版本化编译 | `2026-08-29.r1` | 24,731 |
| `names-cn` | 中文姓氏与男女名字组件的安全静态解析 | `40.37.0.r1` | 530 |
| `population-cn` | 中国年龄/性别人口边际分布 | `WPP2024.r1` | 3,171 |
| `laboratory-cn` | 项目自有中文检验/生命体征目录及精确 LOINC、首选 UCUM 交叉引用 | `2026-08-30.r1` | 18 |
| `loinc-zh-cn` | 完整 LOINC 2.83 核心表、官方中文变体、UCUM 候选单位、SYSTEM Part 与 panel | `2.83.r1` | 365,722 |
| `nhc-procedure-clinical` | 已定义 Contract 与 Schema，编译器暂缓实现 | 暂无 | 暂无 |

表中的构建标识来自当前开发环境中已经验证的 Candidate。本仓库分发编译器、运行时、
合成测试 Fixture，以及允许公开分发的 `laboratory-cn` starter Release。`tmp/`、`.work/`
和 `dist/` 均被 Git 忽略，因此克隆仓库不会附带私有来源工作簿或其他本地 Candidate。

当前已经实现的基础设施包括：

- XLSX 流式提取、规范化、校验与来源指纹检查；
- 确定性 SQLite 产物，以及 FTS5 trigram 和双字 bigram 中文搜索；
- Parquet、zstd 压缩 SQLite、校验报告、Diff 和 Manifest；
- 不可变 Release 修订，以及与上一 Release 的差异比较；
- 本地安装时校验压缩前后 SHA256、限制解压大小，并执行 SQLite 完整性检查；
- 已安装版本的查看、切换与回退；
- 药品、疾病、LOINC 和精选检验目录的精确查询与文本搜索命令；
- 完整 LOINC 2.83 编译，包含 112,405 个核心概念和 96,518 个官方中文显示；
- 项目自行编写的中文检验/生命体征目录，以及精选 LOINC 2.83/UCUM 交叉引用；
- 中国合成姓名、地址、`100` 电话和 `990000` 模拟居民号码的确定性生成；
- 固定 Synthea commit 的 profile 投影、FHIR R4 身份本地化和内部 HTTP 服务；
- Ed25519 签名公共 starter Registry、默认信任根、`init` 和离线 `doctor`；
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
distribution/      签名公共 Registry 与允许公开分发的 starter Release
tmp/               本地原始输入，Git 忽略
.work/             来源快照与本地工作数据，Git 忽略
dist/              不可变的本地 Candidate，Git 忽略
```

## 环境要求

最终用户只需要适用于当前平台的 `cn-health 0.2.1` 原生发行包，不需要 Python、Rust 或
来源工作簿。源码开发环境需要：

- Git；
- Python 3.12；
- [`uv`](https://docs.astral.sh/uv/)；
- Rust 1.96，用于构建原生运行时；
- Node.js 22 和 pnpm 11，仅在开发 npm 启动器时需要。

构建真实数据集还需要 Dataset Contract 中声明的精确来源文件。单元测试与集成测试
使用合成 Fixture，不依赖第三方 XLSX 文件。

## 快速开始

从 GitHub Releases 安装适用于当前平台的 `cn-health 0.2.1` 后，初始化签名 starter 数据
并执行真实查询：

```bash
cn-health init
cn-health laboratory search 血糖 --json
cn-health doctor
```

`init` 使用 CLI 内置的 Registry 地址和固定公钥，安装项目自有的 18 条精选检验/生命体征
数据；下载后查询和 `doctor` 均可离线运行。该 starter 不是官方完整 LOINC 中文包。

贡献者 clone 仓库后使用一条命令建立开发环境并完成同一条真实查询：

```bash
scripts/bootstrap-dev.sh
```

## 来源数据

来源获取采用显式、本地模式。编译器不会扫描 `tmp/`，不会按修改时间选择文件，也不会
从上游 PDF 或网站进行同步。每次构建都必须传入精确的来源路径。

当前声明的第三方工作簿输入如下：

| Dataset | 输入约束 | 工作表 | 预期 SHA256 |
|---|---|---|---|
| `nhsa-drugs` | 由 `DRUG_SOURCE` 指定的药品分类与代码工作簿 | `总表` | `9f7bee4c098d4b0f9fff0f6f9b7c8b580b011d0d3c8b5f6364a3799c76772d67` |
| `nhc-icd10-clinical` | 由 `DIAGNOSIS_SOURCE` 指定的疾病分类国家临床版工作簿 | `2.0（2022版）` | `e927d8ec0d25a64125e24b26dcc3987b0021b5d8b94c0f4d7ae7e05f1592af52` |

药品编译器只读取声明的工作簿 `总表`。`tmp/` 中下载的药品 PDF 不参与构建。手术操作
工作簿也不会被读取，因为手术分类开发已经暂缓。

`laboratory-cn` 与上述导入工作簿不同，它的来源是仓库内的
[`datasets/laboratory-cn/catalog.csv`](datasets/laboratory-cn/catalog.csv)。其中的中文显示、
概念选择、分类、结果类型、首选 UCUM 单位和整理说明由项目自行编写；LOINC 与 UCUM
标识仍然指向各自的外部标准。

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
  --source datasets/laboratory-cn/catalog.csv \
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

## 精选检验概念

`laboratory-cn@2026-08-30.r1` 包含当前已验证消费者所需的 18 个检验与生命体征概念。
它将项目自行编写的中文显示和目录元数据，与精确的 LOINC 2.83 编码及首选 UCUM 单位
组合在一起，并使用与其他编译器相同的 Candidate Contract、确定性 SQLite/Parquet
打包、Manifest 校验、FTS 和双字索引。

这个小型目录不是官方完整 LOINC 中文语言包。独立的 `loinc-zh-cn@2.83.r1` Candidate
包含全部 112,405 个核心概念和 96,518 条官方中文翻译；只需要项目精选小范围概念时，
消费者仍可使用 `laboratory-cn`，无需加载完整术语库。详见
[`datasets/laboratory-cn/README.md`](datasets/laboratory-cn/README.md)。

## 本地安装与查询

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

仓库提供一个由 CLI 固定公钥验证的公共 starter Registry，目前只包含 Manifest 中明确
设置 `releaseEligible: true` 的 `laboratory-cn@2026-08-30.r1`。其他 Candidate 不会因为
本地已经构建就自动获得公开分发资格。

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

## npm 启动器

`npm/cn-health` 是轻量启动器。它只向原生 CLI 转发参数、标准输入输出、信号和退出码，
不包含数据或查询逻辑。

本地开发时，将它指向已经构建的二进制文件：

```bash
pnpm install --frozen-lockfile
cargo build --release -p cn-health

CN_HEALTH_BINARY="$PWD/target/release/cn-health" \
  node npm/cn-health/bin/cn-health.js \
  --data-dir .work/runtime dataset list --json
```

tag 发行工作流为 Linux x64、macOS x64/arm64 和 Windows x64 构建原生归档及可选的
`@cn-health/cli-<platform>-<arch>` npm 平台包。npm 发布只有在仓库显式启用并配置 token
时执行。

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

Dataset 解析器和构建测试只使用合成 Fixture，不将真实来源记录纳入测试。修改来源
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
- `laboratory-cn` 是项目精选目录，不是官方完整 LOINC 中文语言包。
- `loinc-zh-cn@2.83.r1` 已通过本地验收，但仍为 `releaseEligible: false`；公开 Registry
  分发前必须完成针对第三方版权通知的产物级复核。
- `synthea-zh-cn` 已覆盖固定 Synthea 版本，51 条歧义均有证据 resolution，但 2,158 条
  仍是机器复核而非临床专家批准，不能表示为官方术语语言包。

## 文档索引

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
