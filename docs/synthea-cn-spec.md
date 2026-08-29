# Synthea 中国本地化与消费者接入 Spec

状态：已实现；真实 `loinc-zh-cn` Candidate 取决于调用方提供的官方来源包

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
  loinc-zh-cn
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

初始来源策略：

- GeoNames 中国 dump 作为可自动获取的居民点、WGS84 坐标、时区和人口字段来源；
- 国家地名信息库的版本化人工快照作为行政区划代码来源；
- 社区行政区划项目只用于差异检查，不直接覆盖来源记录。

至少包含以下 canonical 表：

```text
administrative_division
  code
  name_zh
  level
  parent_code
  valid_from
  valid_to
  source_version

populated_place
  place_id
  name_zh
  name_ascii
  administrative_code
  latitude_wgs84
  longitude_wgs84
  timezone
  population
  source_version

postal_area
  postal_prefix
  place_id
  latitude_wgs84
  longitude_wgs84
  accuracy
  source_version
```

缺失层级保持缺失，不创建冒充官方区划的补齐节点。历史变更通过有效期或新 Release
表达，不原地改写旧 Release。

### 4.2 `population-cn`

职责：保存聚合人口分布，不生成或保存个人记录。

初始来源策略：

- 结构化年龄/性别数据优先采用可固定版本的统计发布；
- 第七次全国人口普查用于校准省级人口、城乡、教育和家庭规模；
- 地点人口字段只能作为空间采样权重，不能冒充年龄、性别或家庭联合分布。

不同边际分布分表保存，不能在没有联合统计依据时拼成伪联合分布：

```text
population_by_age_sex
population_by_area
population_by_urbanicity
population_by_education
household_size_distribution
```

每行包含统计时期、地域范围、类别、计数、归一化权重、来源和适用说明。Synthea
投影需要插值或回退时，规则及其版本进入 profile Manifest。

### 4.3 `names-cn`

职责：保存生成中文姓名所需的组件与聚合权重，不保存真实完整人员名单。

初始实现采用可替换 source adapter：

- Faker `zh_CN` 只作为接口、算法和测试参考；
- 可明确再利用条件的聚合姓氏/名字统计可构建独立 Candidate；
- 只有完整姓名、来源不明确的语料库不进入 canonical Dataset。

至少包含：

```text
surname
  text
  weight
  is_compound
  romanized

given_name
  text
  gender
  birth_cohort_start
  birth_cohort_end
  weight
  romanized
```

生成器按性别、出生年代和姓名长度策略选择组件。相同 Release、seed 和 ordinal 必须得到
相同姓名；Release 改变必须改变 profile hash，不能悄悄改变旧结果。

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
5. 将真实 `loinc-zh-cn` Candidate 导入 laboratory concepts；
6. 保存原始 Candidate Release ID、canonical hash 和 artifact hash；
7. 导入失败不发布部分 ClinMesh reference release。

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

- 全量药品、诊断以及调用方提供的 LOINC Candidate 可导入独立 reference SQLite；
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
