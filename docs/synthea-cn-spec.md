# Synthea 中国本地化与消费者接入 Spec

状态：已实现；`laboratory-cn` 精选目录已可用，完整 `loinc-zh-cn` 仍由调用方提供官方来源包

## 1. 目标

`cn-health-data` 定位为可被不同医疗软件复用的中国健康参考数据基础设施。Synthea 是
一等支持的消费者，但不拥有 canonical schema，也不改变 Dataset 的通用边界。

本 Spec 交付：

1. `geography-cn`、`population-cn`、`names-cn` 三个版本化 Dataset；
2. 不依赖真实个人记录的确定性中国合成身份规则；
3. 从上述 Dataset Release 生成的版本化 Synthea 中国 profile；
4. 对 Synthea FHIR R4 Bundle 的确定性中国本地化；
5. 使用 Docker 运行固定 Synthea 版本并验证本地化结果；
6. 供 ClinMesh 消费药品、诊断、检验和人口数据的 Manifest/SQLite 边界。

## 2. 当前事实基线

固定 Synthea commit：

```text
d9d07a6eef91ee5144293b42ab64224d84d124f8
```

固定 Synthea 在身份本地化前生成的原始 Patient 包含：

- Massachusetts 地址和 `country=US`；
- `555-*` 电话；
- `us-ssn`、美国驾照和美国护照标识；
- 英文姓名、英文称谓以及西式姓名顺序。

当前 Provider 使用 profile classpath 和“中国”地域生成，再由 cn-health localizer 删除
美国身份语义并写入 profile tag。ClinMesh 只在响应 metadata、Bundle tag、Candidate
依赖和 synthetic identity 规则一致时复用来源身份；兼容 fallback 使用明显虚构的字段。

## 3. 所有权边界

```text
Source snapshots
      |
      v
cn-health-data canonical releases
  geography-cn
  population-cn
  names-cn
  nhsa-drugs
  nhc-icd10-clinical
  laboratory-cn
  loinc-zh-cn (optional official language package)
      |
      +--------------------------+
      |                          |
      v                          v
Synthea projection         ClinMesh reference import
profile + localizer        full authoring reference DB
      |                          |
      v                          v
Synthea R4 material        Hospital Baseline + Scenario Package
```

Canonical Dataset 不保存 Synthea 的美国兼容列，也不保存 ClinMesh 的本院价格、库存、
病例真值或运行状态。消费者投影必须记录所消费的每个 Release ID 和内容哈希。

## 4. Dataset 设计

### 4.1 `geography-cn`

职责：保存行政区划、居民点、坐标、时区、人口权重和邮政前缀等地点参考数据。

当前来源策略：

- 固定 commit 的 AreaCity 社区汇总 CSV 提供三级行政区划名称、层级、父子关系和外部代码；
- 固定下载的 GeoNames 中国 dump 提供居民点、WGS84 坐标、时区和人口权重；
- GeoNames 中国邮政 dump 提供邮政区域坐标与精度；
- 三个来源分别保存版本、哈希和来源角色，组合 Candidate 不把社区汇总表示为官方权威数据。

Candidate 暴露以下 canonical 表和查询视图：

```text
administrative_division
  code
  name_zh
  level
  parent_code
  valid_from
  valid_to
  source_version

place
  code
  geoname_id
  name_zh
  name_ascii
  kind
  admin1_code ... admin4_code
  latitude
  longitude
  timezone
  population
  source_version

populated_place (view over place)

postal_area
  code
  postal_code
  place_name
  admin1_code ... admin3_code
  latitude
  longitude
  accuracy
  source_version
```

缺失层级保持缺失，不创建冒充官方区划的补齐节点。历史变更通过有效期或新 Release
表达，不原地改写旧 Release。

### 4.2 `population-cn`

职责：保存聚合人口分布，不生成或保存个人记录。

当前 Candidate 从联合国《世界人口展望 2024》Medium projection 中只选择 `CHN`，将来源
的千人单位确定性转换为人数，并保存 1950 至 2100 年的五岁年龄组、性别计数和归一化
权重。canonical 表为 `population_age_sex`。

当前 Dataset 不包含省级人口、城乡、教育或家庭规模，也不会用彼此独立的统计拼成伪联合
分布。地点人口字段只作为空间采样权重。Synthea 投影所用参考年份、插值或回退规则及其
版本进入 profile Manifest。

### 4.3 `names-cn`

职责：保存生成中文姓名所需的组件与聚合权重，不保存真实完整人员名单。

当前 Candidate 固定 Faker 40.37.0 的 `zh_CN` person provider 源文件，通过 Python AST
只读取 `last_names`、`first_names_male` 和 `first_names_female` 的声明字面量，不导入模块，
也不执行来源代码。canonical 表为：

```text
name_component
  code
  kind
  gender
  text
  weight
  is_compound
  source_duplicate
  source_ordinal

surname (view over name_component)
given_name (view over name_component)
```

姓氏沿用来源权重，名字列表按重复频次形成权重。Dataset 不包含完整人员身份记录或
出生年代统计。生成器按性别和确定性权重选择组件；相同 Release、seed 和 ordinal 必须
得到相同姓名，Release 改变必须改变 profile hash，不能悄悄改变旧结果。

## 5. 合成身份规则

身份生成是版本化算法，不是个人 Reference Dataset。

默认规则：

- 主标识使用项目自有 synthetic person ID/MRN namespace；
- 模拟居民身份号码使用非签发的 synthetic region namespace、出生日期、确定性顺序码和
  GB 11643 校验位，并明确标记 `synthetic=true`、`authority=none`；
- 默认联系方式使用不属于中国移动号段的 `100` synthetic prefix；
- 地址由真实行政区划名称与明显虚构的道路、门牌模板组成；
- 邮箱使用 `.test` 保留域；
- 不输出美国 SSN、驾照、护照 system，也不把模拟号码声明为政府签发标识；
- 所有字段由 `profile release + source patient id + ordinal` 确定性生成。

需要外观上属于真实手机号段或真实区划码的兼容模式必须由消费者显式配置测试号段和
namespace，不能成为默认行为。

## 6. Synthea Profile Artifact

Profile 是 canonical Release 的消费者投影，不是 P0 Dataset。每个 profile 固定：

```text
profile schema version
supported Synthea commit
geography release ID/hash
population release ID/hash
names release ID/hash
projection compiler version/commit
synthetic identity algorithm version
createdAt
content hash
```

目录至少包含：

```text
synthea-cn-profile/
  manifest.json
  synthea.properties
  names.yml
  geography/demographics.csv
  geography/zipcodes.csv
  geography/timezones.csv
  providers/hospitals.csv
  providers/primary_care_facilities.csv
  providers/urgent_care_facilities.csv
  payers/insurance_companies.csv
  payers/insurance_plans.csv
  payers/insurance_eligibilities.csv
  policy/identity.json
```

Synthea 当前 demographics schema 的 race/ethnicity 列是美国兼容接口。投影可以生成运行
所需兼容值，但必须在 Manifest 中标记为 projection policy，不能写回 `population-cn`
并表示为中国人口统计事实。

## 7. FHIR R4 本地化

本地化器以 Synthea 原始自包含 collection Bundle、profile Manifest 和 seed 为输入，
输出仍为合法、自包含的 FHIR R4 Bundle。

允许改变：

- Patient、Practitioner 和相关 Organization 的中文显示信息；
- Patient 姓名顺序、地址、电话、邮箱与 synthetic identifiers；
- 地址 country、时区和经纬度；
- profile 明确拥有的 payer/provider 展示。

必须保持：

- 所有临床资源 ID；
- Condition、Observation、Medication 等来源编码；
- 资源引用闭包；
- 临床日期、数值、单位和状态；
- 同一输入和 seed 的字节级 canonical 输出。

本地化器删除美国 SSN、驾照和护照标识，保留 Synthea 自身 UUID 作为来源标识，并增加
明确的 synthetic person/MRN identifier。

### 7.1 Runtime clinical display projection

Python 库的 `SyntheaBundleLocalizer` 默认只执行身份本地化。HTTP service 在此之后必须
执行 display 投影，且启动时必须显式提供
`CN_HEALTH_SYNTHEA_TRANSLATION_CATALOG_PATH`（或 `--translation-catalog`）与
`CN_HEALTH_SYNTHEA_CLINICAL_DISPLAY_PROJECTION_ID`（或
`--clinical-display-projection-id`），以及
`CN_HEALTH_SYNTHEA_EXPECTED_CATALOG_SHA256`（或
`--expected-catalog-sha256`）；不得从仓库布局、文件名或日期猜测。expected hash 必须为
64 位小写十六进制，并在 service 启动时与 catalog 的 canonical SHA-256 严格相等；不匹配
必须阻止启动，避免同一 projection ID 在重启后指向不同内容。

投影只接受 `approved`、`human-reviewed` 和 `machine-checked`，不接受
`machine-draft`。任何 allowlisted clinical display 缺失翻译时，整个请求以
`TRANSLATION_GAP` 失败，不返回英中混合 Bundle。`Claim`、
`ExplanationOfBenefit` 及依赖它们的引用闭包由 projector 删除。

`/health` 和成功响应 metadata 均包含 `clinicalDisplay`，其字段为
`projectionId`、`catalogSha256`、固定 `language: zh-CN`、`recordCount` 和固定
`reviewMode: experimental-preview`。请求路径只读取固定本地 catalog，不调用外部翻译
API。该 review mode 是明确的 experimental distribution boundary：术语权利复核完成且
`translation.yaml` 允许发布前，不得把输出描述为 release-eligible 公开发行物。

## 8. ClinMesh 接入

### 8.1 人口与身份

ClinMesh 不再维护姓名、地址、身份证和手机号常量。它消费固定 Synthea profile 或身份
policy artifact，并把 Release ID/hash 保存到 Synthetic Patient Profile Revision。

旧 Profile Revision 继续按旧算法读取；新数据 Release 只影响之后创建的 revision。

### 8.2 临床参考数据

ClinMesh authoring reference database 新增 `cn-health-data` Candidate adapter：

1. 校验 Candidate Manifest schema、Dataset ID、Release ID 和 SQLite SHA256；
2. 以只读模式打开 SQLite 并检查 application ID/integrity；
3. 将 `nhc-icd10-clinical` 导入 diagnosis concepts；
4. 将 `nhsa-drugs` 导入 medication products；
5. 将项目自有 `laboratory-cn` Candidate 导入 laboratory concepts；
6. 若调用方提供完整 `loinc-zh-cn` Candidate，则通过同一 reference concept 边界导入；
7. 保存原始 Candidate Release ID、canonical hash 和 artifact hash；
8. 导入失败不发布部分 ClinMesh reference release。

完整国家参考库只存在于 build/authoring plane。Hospital Baseline Compiler 仍按病例闭包
选择本院子集，普通运行时和 reset 不读取全量 Candidate。

Mapping package 必须使用 `system + version + code` 精确连接 Synthea SNOMED/RxNorm/LOINC
与 Candidate 中的目标概念。中文显示文本只能用于搜索和候选建议，不能静默成为正式
mapping。

## 9. TDD 与验证

### 9.1 Dataset 测试

- source hash、结构、版本和记录数变化失败关闭；
- canonical SQLite/Parquet/Manifest 可重复；
- 权重非负且同一分布归一化；
- 行政层级无环、父节点存在、坐标和日期有效；
- 姓名来源不包含个人级附加字段；
- 相同 seed 输出一致，不同 seed 在样本中产生变化。

### 9.2 Profile 测试

- 所有依赖 Release/hash 进入 Manifest；
- Synthea 资源文件通过固定 commit 的真实加载；
- profile 内容变化导致 content hash 变化；
- canonical Dataset 不出现 Synthea 专有美国列。

### 9.3 Bundle 测试

对固定 raw fixture 做 red/green contract：

- 输出 Patient 使用中文姓名和中国地址；
- `country=CN`，无 Massachusetts、`555-*`、`us-ssn`、美国驾照或美国护照；
- 默认手机号不落入真实移动前缀策略；
- 临床资源编码、日期、值和单位前后相同；
- 引用闭合且 FHIR parser 可读；
- 相同输入、profile 和 seed 输出 hash 相同。

### 9.4 Docker 验收

固定 Synthea commit 构建非 root Docker 镜像。至少生成：

```text
fever
type-2-diabetes
hypertension
```

每个病种生成至少 10 人，并输出机器可读验证报告。报告必须证明：

- 100% Patient 通过本地化合同；
- 资源引用闭合；
- 原始临床编码集合与本地化后一致；
- 双 seed、日期范围、时区、profile hash 和 Synthea commit 已固定；
- 容器运行时不下载 latest 数据。

### 9.5 ClinMesh 验收

- 全量药品、诊断与 `laboratory-cn` Candidate 可导入独立 reference SQLite；调用方提供的
  完整 `loinc-zh-cn` 使用同一导入边界；
- 三个病种关键映射目标实际存在于导入 Release；
- Synthetic Patient Profile 不再依赖姓名、地址或手机号常量；
- 安装后的 Scenario Package 在 Synthea、`cn-health-data` 和外网离线时可运行和 reset；
- 新 Release 不改变旧 Profile Revision 或旧 Package hash；
- 真实 Docker Provider 的端到端生成、编译、保存、安装和 reset 通过。

## 10. 实施顺序

1. Dataset Contract、schema 和合成 fixture；
2. `geography-cn` 真实 Candidate；
3. `names-cn` 真实 Candidate 与确定性身份生成；
4. `population-cn` 真实 Candidate；
5. profile projector 与 Bundle localizer；
6. Docker 三病种验收；
7. ClinMesh Candidate importer 与 Profile provenance；
8. ClinMesh 端到端验证和文档更新。

每个行为切片采用 red-green-refactor。每个 commit 后运行 `code-simplifier`，全部交付后
运行 `find-simplifications`，只记录有证据的后续简化建议。

## 11. 非目标

- 不保存真实患者姓名、身份证、电话或住址；
- 不把 Synthea schema 变成 canonical Dataset schema；
- 不把全量国家参考库复制到 ClinMesh operational database；
- 不用名称模糊匹配自动批准临床映射；
- 不在本阶段实现住院、手术或真实医保结算；
- 不要求 Synthea 或 ClinMesh 普通运行时在线访问来源网站。
