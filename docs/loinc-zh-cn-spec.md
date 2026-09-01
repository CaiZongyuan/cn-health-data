# 完整 `loinc-zh-cn` Candidate 构建 Spec

状态：T1-T3 已由合成来源包验证；T0/T4 受官方来源与权利审查阻塞

对应任务：[GitHub Issue #1](https://github.com/CaiZongyuan/cn-health-data/issues/1)

本文使用“必须”“不得”“应”表达规范性要求。本文不记录未经核验的 LOINC 版本、文件名、
ZIP 成员路径、字段名、哈希或授权结论；这些值必须在取得官方来源包并完成来源审查后写入
Dataset Contract 和布局合同。

## 1. 目标

从调用方显式提供、合规取得且版本固定的官方 LOINC 核心包和简体中文 Linguistic
Variant 包，构建一个完整、不可变、可验证的本地 Candidate：

```text
loinc-zh-cn@<official-loinc-version>.r<build-revision>
```

完成后的 Candidate 必须：

1. 包含固定版本的全部 LOINC 核心记录，而不是只有中文翻译或项目精选记录的子集；
2. 将官方简体中文显示按 code 左连接到核心记录，未翻译记录保留英文名和
   `zh_display = NULL`；
3. 保留检索和消费者需要的 LOINC 六轴、分类、状态及固定的 source-native 元数据；
4. 以规范化表保存官方来源支持的候选 UCUM 单位、SYSTEM/specimen part 语义和
   panel/member 关系；
5. 生成确定性的 SQLite、压缩 SQLite、逐表 Parquet、验证报告、Diff 和 Manifest；
6. 如实记录来源、版本、哈希和权利边界，且不把仓库 MIT License 扩展到第三方数据。

本 Spec 的“完整”只表示核心表记录集合与固定官方版本一致，不表示每条记录都有中文显示、
候选单位、标本 part 或 panel 关系。

## 2. 当前事实基线

仓库当前已有：

- `datasets/loinc-zh-cn/dataset.yaml` 的 planned 合同；
- `datasets/loinc-zh-cn/schema.sql` 的最小 `loinc`、FTS5 和 bigram schema；
- 可配置 ZIP 成员路径、核心 CSV 与中文 CSV join、重复 code 拒绝；
- 基于合成 fixture 的 SQLite、FTS 和 bigram 测试；
- Rust `loinc get/search`，读取 `code`、`long_common_name` 和 `zh_display`。

仓库当前没有：

- 经核验的官方来源包及来源指纹；
- 真实版本的布局合同和 Candidate Manifest；
- `cn-health-build build loinc-zh-cn` 构建入口；
- 完整记录、单位、specimen part 和 panel/member 的 canonical 模型；
- 真实 `data.sqlite` 或可发布的逐条产物。

因此，在第 4 节的启动门槛全部满足前，实现状态必须保持 source-blocked，不得把合成
fixture 结果描述为真实 Candidate。

## 3. 范围边界

### 3.1 包含

- 本地官方来源包的指纹、私有 content-addressed snapshot 和严格解析；
- 英文核心表与官方简体中文显示的确定性 join；
- LOINC code、六轴、英文名称、中文显示、状态、分类和 ORDER_OBS；
- 在布局合同中明确列出的其他 source-native 字段；
- 官方来源中的候选 UCUM 单位、SYSTEM/specimen part 和 LOINC panel/member 边；
- 多表 canonical hash、逐表 Diff、SQLite/Parquet 打包和验证报告；
- 现有 Rust 精确 code 查询、中文/英文搜索兼容性；
- Candidate 的本地构建和验证。

### 3.2 不包含

- 医院服务目录、医院内部编码、价格、TAT、执行科室或可用范围；
- 临床参考范围、危急值、报告模板、模型配置或决策支持；
- 按某个消费者、医院或病种筛除 LOINC 分类；
- 对缺失中文的记录进行机器翻译、人工补译或复用 `laboratory-cn` 显示；
- 将候选单位表示为唯一或首选单位；
- 将 SYSTEM part 自动映射为本地标本分类；
- 自动登录、下载、抓取或选择“最新”LOINC 包；
- 提交官方原始包、私有 snapshot 或条款不允许再分发的逐条生成产物；
- 在本任务中修改既有 `laboratory-cn` Candidate 或不可变 Release。

## 4. 启动门槛

实现真实 Candidate 前，维护者必须完成一次来源 intake，并冻结下列信息：

| 项目 | 必须记录的值 | 构建期检查 |
|---|---|---|
| 核心包 | 官方名称、版本、原始文件名、取得方式/URL、SHA-256、字节数 | hash 与 size 完全相等 |
| 中文包 | 官方名称、目标 LOINC 版本、语言/地区、原始文件名、取得方式/URL、SHA-256、字节数 | hash、size、语言和版本完全相等 |
| 包模式 | `combined` 或 `split` | CLI 输入数量与模式一致 |
| ZIP 布局 | 成员清单、必需成员、成员大小、编码、分隔符、完整有序 header | 逐项完全匹配 |
| 版本证据 | 包内版本字段/元数据成员，或经审查且绑定来源 hash 的声明 | 核心与中文目标版本一致 |
| 记录基线 | 核心记录数及各辅助表记录数 | 与合同固定值相等 |
| 权利 | 适用条款、取得资格、允许用途、允许产物类型、署名、再分发结论、审查人和日期 | Manifest 如实投影，无 CLI 覆盖 |

来源审查证据应保存为仓库可提交的元数据文档，例如
`datasets/loinc-zh-cn/source-review.md`；不得在其中复制逐条数据、访问凭据或不允许公开的
条款正文。

只有以下条件全部成立时，才可以把真实构建实现标记为可验收：

- 两个输入角色均有可重复取得或可审计的来源记录；
- 所有必需成员和 header 已从实际包核验；
- 核心版本与中文包目标版本的兼容关系已确认；
- 单位、part link 和 panel 文件的真实语义已确认；
- `rights.redistribution` 和 `rights.release_eligible` 有书面依据。

如果官方包不提供满足单位、specimen part 或 panel 语义所需的成员，应先修订本 Spec 或
取得相应官方附件，不得从文本字段猜测结构化关系。

## 5. 来源合同

### 5.1 Dataset Contract

完成 intake 后，`datasets/loinc-zh-cn/dataset.yaml` 必须由 planned 占位合同改为固定来源
合同。`source` 至少区分 `core` 与 `linguistic_variant` 两个角色；两个角色在
`combined` 模式下可以引用同一物理 ZIP 和同一 hash，但 Manifest 只记录一次物理来源并
列出两个角色。

每个物理来源必须记录：

```text
authority
authority_role
format
acquisition
original_filename
path_hint
source_url
declared_version
sha256
size_bytes
upstream_sync: false
```

合同还必须固定：

- `dataset_schema_version: 2`；
- `validation.expected_loinc_count` 和各辅助关系的基线计数；
- 可接受的 status、ORDER_OBS、part link type 和 panel relationship 值；
- 记录数相对变化阈值，供后续 Release Diff 使用；
- `runtime.minimum_sqlite_version`；
- rights basis、evidence、attribution、reviewed-by/date 和 allowed artifact types。

如果通用 Dataset JSON Schema 尚不支持这些字段，必须先向 schema 增加显式定义和测试，
不得利用 `additionalProperties` 隐式塞入关键合同。

### 5.2 布局合同

新增 `datasets/loinc-zh-cn/layout.yaml`，版本从 `1` 开始。它必须声明而不是猜测：

```text
package_mode
archive limits:
  maximum entry count
  maximum total uncompressed bytes
  maximum per-member uncompressed bytes
  maximum compression ratio
core member:
  archive role, exact member path, uncompressed hash/size, encoding, delimiter, ordered headers
  canonical field-to-source-column mapping
  preserved metadata mapping
linguistic variant member:
  archive role, exact member path, encoding, delimiter, ordered headers
  code/display/language/version column mapping and row filter
unit members:
  exact member paths, mappings, list grammar and unit kind
part and part-link members:
  exact member paths, mappings and SYSTEM selection rule
panel member:
  exact member path, mappings, row filter and member ordering rule
version assertions:
  evidence member/field and expected values
```

所有 header 必须以完整有序列表固定。新增、缺失、重复或重排字段都视为来源布局变化并使
构建失败，直到合同经过审查和显式升级。每个不进入 canonical 数据的来源字段必须在
layout 中列为 `ignored_columns` 并附简短原因；不得无声丢弃新增列。

### 5.3 CLI 输入

构建入口为：

```bash
uv run cn-health-build build loinc-zh-cn \
  --source /absolute/path/to/official-core.zip \
  --translation-source /absolute/path/to/official-zh-cn.zip \
  --build-revision 1 \
  --sequence <registry-sequence>
```

规则：

- `split` 模式必须提供 `--translation-source`，且两个路径分别匹配各自 hash；
- `combined` 模式不得提供 `--translation-source`，中文成员从 `--source` 读取；
- 路径必须由调用方显式指定；不得扫描 `tmp/`、按 mtime 选择文件或访问网络；
- `--base-release` 沿用现有 Candidate Diff 语义；
- 正常构建沿用 dirty worktree 拒绝策略；测试可以显式注入固定 git commit 和时间。

## 6. 安全解析合同

### 6.1 ZIP

在读取 CSV 前必须完成外层 SHA-256 和 size 检查。ZIP 检查必须拒绝：

- 绝对路径、`..`、反斜杠路径、NUL、盘符路径或规范化后重复的成员名；
- 不在 layout 中的必需成员缺失，或同名成员出现多次；
- 加密成员、symlink、损坏 CRC 或不允许的压缩算法；
- entry 数、单成员解压大小、总解压大小或压缩比超过固定上限；
- 实际成员大小与 layout 指纹不符。

解析器只通过 `ZipFile.open()` 流式读取声明成员，不把 ZIP 解压到文件系统。失败后可以保留
私有 content-addressed source snapshot，但不得留下 Candidate 目录或部分发布物。

### 6.2 CSV 与文本

- 编码、BOM、delimiter、quote 和 newline 行为由 layout 固定；
- 使用标准 CSV parser，不按字符串切分行或列；
- 文本去除字段两端空白后做 Unicode NFC；空字符串转为 `NULL`；
- 不改变 code、UCUM 大小写或 source-native 枚举的内部字符；
- 必需值为空、解码错误、列数漂移或 CSV 语法错误均原子失败；
- source row 使用从 2 开始的逻辑 CSV record ordinal（header 为 1），仅用于 provenance，
  不参与业务排序。

### 6.3 Join

核心表是记录全集，中文表只能左连接到核心表：

- 核心 code 必须唯一且非空；
- 经过 layout 过滤后，每个 code 最多一个官方简体中文 display；
- 中文包引用未知核心 code 必须失败；
- 中文 display 为空时按无翻译处理，不生成替代文本；
- `long_common_name` 始终来自核心包且必须非空；
- 核心版本、中文包目标版本和合同版本必须一致；
- 输出按 code 的 Unicode code-point 顺序稳定排序。

## 7. Canonical 数据模型

本任务将 `loinc-zh-cn` 的 Dataset Schema 显式升级为版本 2，同时设置
`PRAGMA user_version = 2`。SQLite application ID 保持项目现有值。由于当前没有已发布的
真实 `loinc-zh-cn` Release，这次升级不改写任何既有 Release。

### 7.1 `loinc`

一行代表一个核心 LOINC code。除特别标注外字段均为 SQLite `TEXT`：

```text
code                         primary key
component
property
time_aspect
system
scale_type
method_type
long_common_name             required English source value
short_name
consumer_name
class
class_type                    integer
order_obs
status                       required source value
status_reason
status_text
change_type
definition_description
version_first_released
version_last_changed
panel_type
zh_display                   nullable official Simplified Chinese display
source_metadata_json         required canonical JSON object for layout-allowlisted metadata
source_row                   integer
translation_source_row       nullable integer
source_version
core_source_sha256
translation_source_sha256
```

`source_metadata_json` 只保存 layout 明确列出的、尚未提升为独立列的 source-native 字段。
它使用 RFC 8785 canonical JSON，对空值省略 key；不得把未审查的新列自动装入 JSON。

### 7.2 `loinc_unit`

保存来源明确提供的候选 UCUM 表达式：

```text
loinc_code                   foreign key -> loinc.code
ucum_unit
unit_kind                    layout 固定枚举，例如来源中的 example/example-si 角色
source_member
source_row                   integer
source_sha256
primary key (loinc_code, unit_kind, ucum_unit)
```

单位必须通过固定版本的 UCUM grammar validator。表达式原文在去除外围空白后保留，不进行
“纠正”。同一来源角色中的重复单位、非法单位或未知 code 必须失败。表名和报告必须使用
`candidate`/`example` 语义，不得宣称这些单位是医院首选单位。

### 7.3 `loinc_specimen`

只保存官方 part/link 文件支持的 SYSTEM 轴候选语义：

```text
loinc_code                   foreign key -> loinc.code
part_number
part_name
part_display_name            nullable source value
link_type                    source-native、layout allowlist 值
source_member
source_row                   integer
source_sha256
primary key (loinc_code, part_number, link_type)
```

`loinc.system` 原始文本始终保留。`loinc_specimen` 不得根据字符串、中文翻译或本地规则制造
part，不得把候选 part 表示为采集要求或医院标本目录。

### 7.4 `loinc_panel_member`

保存官方来源中 LOINC code 到 LOINC code 的 panel 边：

```text
panel_code                   foreign key -> loinc.code
member_code                  foreign key -> loinc.code
member_order                 integer; official sequence, or layout-declared source order
relationship                source-native、layout allowlist 值
source_metadata_json         canonical JSON for allowlisted edge metadata
source_member
source_row                   integer
source_sha256
primary key (panel_code, member_order, member_code)
```

所有选入的 panel/member 边必须引用当前核心集合；未知引用、自引用、重复主键或非法顺序均
失败。官方文件中的非 LOINC 行只有在 layout 以已核验的类型字段显式排除时才可跳过。

### 7.5 搜索表

保留现有运行时兼容名称：

```text
loinc_fts(long_common_name, zh_display)
loinc_search_bigram(term, code)
```

FTS5 使用 `trigram` tokenizer。bigram 同时从英文 long common name 和非空中文 display
生成，按 `(term, code)` 去重。搜索表和 SQLite 内部表不计入 canonical record count。

## 8. 验证与报告

`validation.json` 必须是确定性 JSON，并至少包含：

```text
schemaVersion
passed
sourceVersion
loincCount
translatedCount
untranslatedCount
translationCoverage: numerator, denominator, ratio
statusCounts
classCount
panelCount
panelMemberCount
unitCount
loincWithUnitCount
unitCoverage: numerator, denominator, ratio
specimenLinkCount
loincWithSpecimenCount
sourceMembers: role, member, uncompressedSha256, uncompressedSizeBytes, rowCount
```

coverage 的 `ratio` 使用固定六位小数的字符串，分子/分母同时保留，避免浮点和口径歧义。
中文覆盖率分母是全部 `loinc` 行；单位覆盖率分母也是全部 `loinc` 行。状态分布按状态 key
排序，所有计数必须由最终 SQLite 只读复算并与流式 validator 结果一致。

下列任一情况必须使构建失败：

- 来源 hash、size、版本证据、成员路径、成员指纹或 header 不匹配；
- 重复核心 code、重复中文记录、孤立中文记录；
- 核心记录数或辅助表基线不符合合同；
- 非法 UCUM、未知 part/code、未知 panel member 或非法枚举；
- SQLite foreign key、`integrity_check`、application ID、user version 或 schema 检查失败；
- canonical count/hash 与 SQLite 复算不一致；
- 任何产物 hash/size 与 Manifest 不一致。

## 9. Candidate 构建与产物

构建顺序固定为：

```text
resolve clean git commit
  -> validate contracts and rights metadata
  -> hash/size source inputs
  -> snapshot private inputs
  -> inspect bounded ZIP layouts and versions
  -> stream/normalize/join records
  -> validate relationships
  -> build temporary SQLite
  -> integrity/schema/query validation
  -> canonical table hashes
  -> Parquet + zstd + validation + diff
  -> validate Manifest
  -> atomic rename to immutable release directory
```

成功目录为：

```text
dist/loinc-zh-cn/releases/<source-version>.r<revision>/
├── data.sqlite
├── data.sqlite.zst
├── loinc.parquet
├── loinc-units.parquet
├── loinc-specimens.parquet
├── loinc-panel-members.parquet
├── diff.json
├── manifest.json
└── validation.json
```

只有 rights 合同允许的 artifact types 才能生成 Parquet；不允许时 Manifest 和输出目录都
不得声称存在这些文件。SQLite 与压缩 SQLite 是否允许离开本地也由 rights 合同决定。

### 9.1 Canonical identity

canonical 数据表依次为：

```text
loinc
loinc_unit
loinc_specimen
loinc_panel_member
```

每张表按主键排序后使用现有 `canonical-ndjson-v1` 规则计算独立 SHA-256。Manifest 的
`canonical.tables` 保存逐表 `recordCount` 和 `sha256`；顶层 canonical hash 是以下对象的
RFC 8785 SHA-256：

```json
{"tables":[{"table":"...","recordCount":0,"sha256":"..."}]}
```

`canonical.recordCount` 是四张 canonical 表的行数之和；核心版本的官方记录数单独记录为
`validation.loincCount`，两者不得混用。

相同来源 bytes、合同、layout、schema、lockfile、adapter version 和 git commit 必须产生
相同 canonical hash、SQLite hash、压缩 SQLite hash 及各 Parquet hash。`createdAt` 不属于
canonical identity。

### 9.2 Manifest provenance

Manifest 必须记录：

- 每个物理来源的角色、官方 authority、取得方式、版本、原始文件名、URL、hash 和 size；
- 合同、layout、schema、lockfile、git commit 和完整 build input hash；
- Dataset Schema Version 2、adapter version 和编译环境版本；
- canonical 总 hash、逐表 hash/计数；
- SQLite、zstd 和允许生成的 Parquet hash/size；
- validation 和 diff 报告 hash；
- rights、evidence、attribution、allowed artifact types 和 `releaseEligible`。

原始 ZIP 不得成为 Candidate artifact。

### 9.3 Diff 与不可变性

- 已存在的 `<source-version>.r<revision>` 目录不得覆盖；
- 同一官方版本的代码、配置或 metadata 修正使用新的 build revision；
- 新官方版本使用新的 source version；
- `--base-release` 必须属于 `loinc-zh-cn` 且 SQLite hash 匹配其 Manifest；
- 首期只允许相同 Dataset Schema Version 的逐表 Diff，跨 schema Diff 以明确错误拒绝；
- Diff 汇总 added/removed/modified/unchanged，并按表报告变化，provenance 列不计为内容修改。

## 10. 权利与发布门禁

本地 Candidate 构建和公开发布是两个不同动作：

- 条款允许本地处理但不允许再分发时，使用 `redistribution: private` 和
  `releaseEligible: false`；
- 条款仍待结论时，使用 `review-required`，但本 Issue 不进入真实构建验收；
- 只有 evidence 明确覆盖将要发布的 SQLite/压缩 SQLite/Parquet 类型时，才可将
  `releaseEligible` 设为 `true`；
- CLI 不提供忽略、覆盖或临时提升 rights 的参数；
- signed Registry 继续拒绝 `releaseEligible: false` 的 Candidate；
- README 中的版本、数量和覆盖率可以公开，但不得借此公开被限制的逐条内容。

仓库 `LICENSE` 只覆盖项目自有代码和文档，不是 LOINC 数据的 rights evidence。

## 11. Runtime 查询合同

现有 Rust 合同保持兼容：

- `cn-health loinc get <code>` 返回 `code`、`longCommonName`、可空 `zhDisplay`；
- `cn-health loinc search <text>` 同时搜索英文和中文；
- 两字符查询使用 bigram，三字符及以上使用 literal FTS；
- FTS 按 BM25 rank、code 排序，bigram 按 code 排序；限制页读取 `limit + 1` 并报告
  `truncated`；
- 未翻译记录可以通过英文名称和精确 code 查询返回；
- 查询以只读模式打开数据库。

Candidate 验收必须覆盖精确 code、英文 FTS、中文 FTS、中文 bigram、未翻译记录、稳定
排序、第一页/后续 SQL page 边界和 `truncated`。本任务不扩展医院业务字段或模糊映射 API。

## 12. 实施切片

### T0：来源 intake

- 核验两个来源角色、包模式、版本、布局、基线计数和权利；
- 提交不含逐条数据的 source review；
- 将 `dataset.yaml` 从占位合同更新为真实固定合同。

完成证据：合同校验通过，所有 hash/size/version/rights 字段非占位。

### T1：布局、schema 与模型

- 新增真实 `layout.yaml`；
- 将 LOINC Dataset Schema 升级为 2；
- 扩展 records/config models，模型均使用 frozen、`extra="forbid"`；
- 保留现有 Rust 查询需要的表名和列名。

完成证据：合成 schema/contract tests 先失败后通过。

### T2：安全 adapter 与验证

- 实现 bounded ZIP inspection、完整 header/version checks；
- 流式读取核心、中文、单位、part link 和 panel 成员；
- 实现 join、关系闭包、UCUM 和基线验证；
- 输出完整 validation report。

完成证据：正向 fixture 和第 13.2 节全部负向用例通过。

### T3：多表 Candidate builder

- 新增 `sources/loinc/build.py` 和 LOINC 专用多来源 builder；
- 生成多表 canonical identity、逐表 Parquet、Diff、Manifest；
- 在通用 CLI 中接入 `loinc-zh-cn` 和 `--translation-source`；
- 保证 staging 与 atomic publish。

完成证据：CLI 合成端到端测试通过，两次构建的 canonical/SQLite hash 相同。

### T4：Runtime 与真实 Candidate 验收

- 扩展 Python SQLite 和 Rust 查询测试；
- 使用本地官方包执行一次 build 和 validate；
- 只记录版本、计数、覆盖率、hash、artifact size 和耗时；
- 更新 README、Source Inventory 和 Implementation Status。

完成证据：本地真实 Candidate 满足第 14 节 Definition of Done。

## 13. 测试规格

### 13.1 正向合成 fixture

fixture 必须模拟 intake 后确认的真实成员层次与 header，但内容全部为项目生成数据，至少
覆盖：

- 有中文和无中文的核心记录；
- active、inactive 及合同允许的其他状态；
- 六轴、class、ORDER_OBS 和保留 metadata；
- 单个单位、多个单位及不同 unit kind；
- SYSTEM part link；
- panel、普通 member 和嵌套 panel member；
- combined/split 中实际采用的模式；
- UTF-8 BOM、quoted comma 和规范化文本。

### 13.2 负向测试

至少覆盖：

- 外层 hash/size 错误；
- 版本不一致、语言不是简体中文；
- 缺少必需成员、额外/缺失/重排 header、重复 header；
- 绝对路径、`..`、反斜杠、symlink、重复成员、CRC 损坏；
- entry/单成员/总解压大小和压缩比越界；
- 解码、CSV 语法、必需空值错误；
- 重复核心 code、重复中文 code、孤立中文 code；
- 非法 UCUM、未知 part、未知 panel/member、自引用和重复 panel edge；
- 核心及辅助记录数基线不符；
- dirty worktree、已有 release 目录、错误 base Dataset/hash/schema version；
- rights 缺字段或 `releaseEligible` 与证据/allowed artifact types 冲突；
- 任一失败均没有可见的部分 Candidate。

### 13.3 SQLite 与可复现性

- `PRAGMA integrity_check = ok`、`foreign_key_check` 为空；
- application ID 与项目常量一致，`user_version = 2`；
- schema/table/index/FTS 定义与固定 SQL 一致；
- 精确 code、FTS、bigram、稳定排序和有界 page 查询正确；
- canonical 表行数、逐表 hash 和总 hash 可复算；
- 同输入两次构建的 canonical、SQLite、zstd 和 Parquet hash 相同；
- Manifest 中每个 artifact 的 hash/size 与文件一致。

### 13.4 必跑命令

```bash
uv run pytest
uv run ruff check .
uv run mypy python/compiler/src
cargo test -p cn-health
```

真实来源包只在授权的本地验收环境使用，不进入 CI。CI 仅使用合成 fixture。

## 14. Definition of Done

以下条件必须全部满足：

- 第 4 节来源 intake 和 rights 审查完成；
- `cn-health-build build loinc-zh-cn` 可从显式官方输入原子构建 Candidate；
- `validation.loincCount` 与固定官方核心版本完全一致；
- 每个核心 code 恰有一行，中文缺失保持 `NULL`，没有无来源翻译；
- 单位、specimen part 和 panel/member 关系均来自声明成员且通过引用闭包；
- Manifest 固定所有来源、build input、canonical 和 artifact hash/size；
- 相同输入重复构建得到相同 canonical、SQLite、zstd 和 Parquet 内容；
- SQLite integrity、application ID、schema、FTS、bigram、精确查询和 page 测试通过；
- 验证报告包含中文覆盖率、未翻译数、状态分布、panel 数量和单位覆盖率；
- 所有失败模式 fail closed，且不发布部分 Candidate；
- 既有 `laboratory-cn` Candidate 和其他不可变 Releases 的 hash 不变；
- README、Source Inventory、Implementation Status 只在真实验收后更新为实际版本和计数；
- 官方原始包、private snapshots、真实 Candidate 产物未被 Git 跟踪；
- 第 13.4 节命令全部通过。

在上述条件满足前，`loinc-zh-cn` 必须继续显示为 planned/source required，且不得加入公开
Registry。
