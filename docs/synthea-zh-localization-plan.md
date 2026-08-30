# Synthea 临床内容中文化实施计划

状态：固定基线 Milestone B 已实现（实验性 machine-checked 目录；51 条证据复核已解决，
其中 18 条记录为上游 module 问题）

基线：

- Synthea commit `d9d07a6eef91ee5144293b42ab64224d84d124f8`；
- `synthea-cn@2026-08-29.r3`；
- FHIR R4 collection Bundle；
- `geography-cn@2026-08-29.r1`、`names-cn@40.37.0.r1`、
  `population-cn@WPP2024.r1`。

## 1. 决策摘要

本计划只完成 Synthea 临床内容的简体中文显示，不改变临床事实或编码体系。

明确决策：

1. 保留所有来源 `system + version + code`；来源没有 `version` 时继续保持缺失，不伪造
   术语版本。不实施 SNOMED、RxNorm、LOINC、CVX 到中国编码体系的映射；
2. `Claim` 和 `ExplanationOfBenefit` 不进入首期中文 Bundle，医保、费用、币种和
   理赔模型后续单独设计；
3. FHIR 字段名、资源 ID、引用、状态码、日期、数值和单位代码保持不变；
4. 中文化对象是用户可见的名称、说明和受控文本；
5. 翻译在构建阶段通过小批次 API 完成，普通生成和运行时不访问翻译 API；
6. 翻译 API 只接收去重后的术语和有限上下文，不接收患者 Bundle；
7. 每个翻译批次是数据文件，不为每个批次复制一份 Python 脚本；
8. Python 实现按职责拆分，并放在 `cn-health-compiler` 包中。`scripts/` 只允许放置
   薄编排入口；
9. 机器翻译不能自动标记为人工审核或正式批准；
10. 发布物必须固定 Synthea commit、翻译目录版本、内容哈希、Prompt 版本和构建器版本。

首期完成标准不是“FHIR JSON 中不存在英文字符”，而是：

> 当前支持范围内，所有面向用户显示的临床概念都有中文显示；机器使用的标准字段和值
> 继续保持合法 FHIR R4 表达。

## 2. Synthea 的生成模型

Synthea 不是按一个疾病生成一份孤立病历。它让一个合成人从出生开始按时间步推进，同时
运行生命周期、就诊、保险等基础模块，以及所有启用的疾病模块。多个模块可以在同一次
就诊中写入诊断、检验、药物或操作，最后导出一份纵向病历。

固定基线包含 242 个 module JSON 文件和 5,316 次编码显示。将字符串型和数字型 code
统一规范为字符串后，静态清单包含 2,149 个不同的 `system + version + code` 键：

| 来源系统 | 唯一代码数 |
|---|---:|
| SNOMED-CT | 1,224 |
| LOINC | 417 |
| RxNorm | 483 |
| DICOM-SOP | 7 |
| DICOM-DCM | 6 |
| NUBC | 6 |
| CVX | 5 |
| NullFlavor | 1 |

这些数字只覆盖 module JSON。FHIR exporter 内置的 HL7、CVX、CMS、状态、分类和其他
显示文本必须由清单工具另行发现，不能假设 module 扫描已经代表全部输出。

## 3. 范围

### 3.1 首期包含

- 当前发热、高血压和 2 型糖尿病验证 corpus；
- `Patient`、`Practitioner`、`Organization` 的既有中国身份本地化；
- `Encounter`；
- `Condition` 和 `AllergyIntolerance`；
- `Observation` 和 `DiagnosticReport`；
- `Medication`、`MedicationRequest` 和其他实际出现的用药资源；
- `Procedure`；
- `Immunization`；
- `CarePlan`、`CareTeam` 和 `Goal`；
- `Device` 和 `SupplyDelivery`；
- `ImagingStudy`、`Media` 等实际出现且包含可见术语的资源；
- FHIR 中常见分类、状态和角色的中文呈现；
- 固定基线中后续启用模块产生的同类资源。

### 3.2 首期排除

- `Claim`；
- `ExplanationOfBenefit`；
- 中国医保、支付、定价、币种和理赔规则；
- SNOMED 到中国 ICD、RxNorm 到中国药品等跨体系编码映射；
- 中国疾病发生率、筛查策略、诊疗路径或用药策略校准；
- 自由文本临床笔记。当前基线未启用 clinical note export；
- 将 FHIR JSON 字段名翻译成中文；
- 将标准状态码从 `active`、`final`、`male` 等改成中文代码；
- 修改数值、剂量、日期、单位代码或资源引用。

### 3.3 后续范围

自由文本病历、中国临床模型和中国理赔模型必须各自建立新 Spec，不能作为本计划的
“剩余翻译”顺带实现。

## 4. 字段处理分类

清单工具必须为每个可出现的字段路径指定一种处理策略：

| 策略 | 含义 | 示例 |
|---|---|---|
| `KEEP` | 原样保留 | `id`、`reference`、`birthDate`、结果数值 |
| `DISPLAY_LOOKUP` | 按代码精确查询中文显示 | 疾病、检验、药品、操作、疫苗 |
| `UI_LABEL` | 数据值保留，由渲染层显示中文 | `status=final`、`gender=male` |
| `TEMPLATE_LOOKUP` | 按完整来源字符串或模板 ID 查中文 | 受控剂量说明、模块模板文字 |
| `IDENTITY_LOCALIZER` | 由现有身份本地化器处理 | 姓名、地址、电话、机构 |
| `EXCLUDE` | 首期不输出 | `Claim`、`ExplanationOfBenefit` |
| `DEFER` | 已识别但需要新 Spec | 自由文本临床笔记、理赔模型 |

禁止使用“递归查找所有字符串然后翻译”的实现。它会误改代码、URL、引用、单位和
机器字段。FHIR projector 必须维护按 `resourceType + JSON path` 定义的允许列表。

### 4.1 主要临床路径

清单和 projector 至少覆盖下列语义路径；最终路径以固定 FHIR exporter 的真实输出为准：

| Resource | 中文显示对象 | 必须保持不变 |
|---|---|---|
| Encounter | 类型、原因、参与者角色、入院/出院分类 | class code、period、references |
| Condition | 疾病、分类、临床/验证状态显示 | system、code、onset、abatement |
| AllergyIntolerance | 过敏原、反应表现、分类显示 | code、状态、日期 |
| Observation | 检验名、组件名、分类、解释显示 | value、unit code、日期、状态 |
| DiagnosticReport | 报告名、分类显示 | result references、日期、状态 |
| MedicationRequest | 药名、原因、受控用药说明 | RxNorm code、剂量数值、频次代码 |
| Procedure | 操作名、原因、部位显示 | SNOMED code、日期、状态 |
| Immunization | 疫苗名、途径、部位显示 | CVX code、日期、剂量 |
| CarePlan/CareTeam/Goal | 计划、活动、原因、角色显示 | code、period、references |
| Device/SupplyDelivery | 器械或耗材名称 | code、数量、日期 |
| ImagingStudy/Media | 检查、模态、部位显示 | DICOM code、UID、附件 |

## 5. 中文输出合同

中文化必须生成一份新的 Bundle，不原地覆盖来源文件。

对受控临床概念：

1. `Coding.system`、`Coding.version` 和 `Coding.code` 不变；
2. 当目录有审核通过的中文显示时，在本地化副本中写入中文 `Coding.display`；
3. 对 `CodeableConcept` 同时写入中文 `text`，保证常见 FHIR 渲染器优先显示中文；
4. 原始英文显示保存在翻译目录的 `sourceDisplay` 中，原始 Bundle 继续作为不可变来源；
5. 没有中文记录时不得猜测，保留来源显示并写入 coverage gap；
6. 一个代码出现多个互相冲突的来源显示时停止合并并要求处理冲突；
7. Bundle `meta.tag` 增加翻译 Release ID 和内容哈希；
8. 输出 Manifest 记录来源 Bundle SHA256、profile、翻译目录和构建器 provenance。

对 `status`、`gender` 等 primitive code，FHIR 数据仍保存标准值。完整中文病历由渲染层
使用同版本 UI label 目录显示，不改变标准代码。

## 6. 目录与发布物设计

建议新增以下仓库结构：

```text
translations/
  synthea-zh-cn/
    translation.yaml
    glossary.yaml
    catalog.jsonl
    ui-labels.jsonl
    overrides.jsonl

schemas/
  translation-record.schema.json
  translation-release.schema.json

python/compiler/src/cn_health_compiler/synthetic/translation/
  __init__.py
  inventory.py
  batches.py
  api.py
  catalog.py
  projector.py
  validation.py

python/compiler/tests/
  test_synthea_translation_inventory.py
  test_synthea_translation_batches.py
  test_synthea_translation_catalog.py
  test_synthea_translation_projector.py
  test_synthea_translation_validation.py
```

生成中间文件不提交 Git：

```text
.work/synthea-translation/
  <synthea-commit>/
    inventory.jsonl
    conflicts.json
    batches/
      pending/
      completed/
      failed/
    review/
    coverage.json
```

发布物：

```text
dist/synthea-zh-cn/releases/<version>/
  catalog.jsonl
  glossary.yaml
  ui-labels.jsonl
  manifest.json
  validation.json
  coverage.json
```

`dist/` 继续保持不可变 Release 语义，不提交来源 Bundle 或患者级数据。

## 7. Translation Record

每个翻译记录至少包含：

```json
{
  "schemaVersion": 1,
  "translationId": "sha256-of-source-key",
  "sourceSystem": "LOINC",
  "sourceVersion": "2.83",
  "sourceCode": "4548-4",
  "sourceDisplay": "Hemoglobin A1c/Hemoglobin.total in Blood",
  "language": "zh-CN",
  "displayZh": "糖化血红蛋白",
  "domains": ["laboratory"],
  "method": "project-curated",
  "reviewStatus": "approved",
  "needsReview": false,
  "provenanceId": "laboratory-cn@2026-08-30.r1",
  "promptVersion": null,
  "model": null,
  "reviewer": null,
  "reviewedAt": null,
  "notes": null
}
```

允许的 review status：

```text
pending
machine-draft
machine-checked
human-reviewed
approved
rejected
```

API 输出只能进入 `machine-draft`。第二次独立机器检查最多提升为 `machine-checked`。
只有明确的人工流程或项目已经评审的来源目录可以进入 `approved`。

同一 `sourceSystem + sourceVersion + sourceCode` 应复用一条首选翻译；版本缺失时使用
明确的 `null`，并由 Release Manifest 固定 Synthea commit。资源上下文只用于发现歧义，
不能导致同一概念在不同 Bundle 中随机产生不同译名。确实存在语境差异时，必须在 schema
中显式增加 designation/use，而不是把上下文藏在 Prompt 中。

`ui-labels.jsonl` 单独保存 primitive code 的渲染标签，例如 Patient gender、FHIR resource
status 和 encounter class。它的键必须包含 code system 或明确的 FHIR path，不能建立一个
全局的 `active -> 活动` 字典，因为同一个 code 在不同字段中可能需要不同中文表达。

## 8. Python 命令设计

固定 Synthea 版本提供 `exporter.code_map.*` 扩展点，但它主要用于给部分 CodeableConcept
增加目标编码，当前 exporter 并未在所有资源路径调用它，映射文件也不携带本计划要求的
审核与 Release provenance。因此它不能作为全量中文显示的唯一实现。以后可以由批准目录
生成兼容 code map，但本计划以独立 projector 和 coverage 为准。

正式逻辑应通过 `cn-health-build` 暴露，建议命令：

```text
cn-health-build synthea translation inventory
cn-health-build synthea translation make-batches
cn-health-build synthea translation translate-batch
cn-health-build synthea translation check-batch
cn-health-build synthea translation merge
cn-health-build synthea translation validate-catalog
cn-health-build synthea translation project
cn-health-build synthea translation coverage
```

一个 Python 模块负责一种职责；同一模块处理任意批次。不要生成
`translate_batch_001.py`、`translate_batch_002.py` 这样的重复程序。批次差异只存在于
`batch-0001.json`、`batch-0002.json` 等输入数据中。

### 8.1 `inventory`

输入：

- 固定 Synthea checkout；
- 支持的 module 集合；
- 固定 FHIR corpus；
- exporter 源码或导出结果。

输出：

- 去重的代码和来源显示；
- 出现次数；
- module、resource type 和 JSON path 上下文；
- 来源显示冲突；
- 未知 code system；
- `KEEP/DISPLAY_LOOKUP/UI_LABEL/TEMPLATE_LOOKUP/EXCLUDE/DEFER` 分类；
- inventory content hash。

Inventory 必须以真实 JSON parser 读取 module，不允许使用正则表达式解析 JSON。

### 8.2 `make-batches`

只选择尚无有效中文翻译的去重记录。默认每批 20 至 40 条，同时受最大字符数或 token
预算限制。批次按 terminology 和 domain 分组，避免把肿瘤、药物、影像等互不相关内容
混在同一个上下文中。

批次必须包含：

- batch ID；
- inventory hash；
- Prompt 版本；
- 每条记录的稳定 translation ID；
- system、code、英文显示；
- domain 和少量非患者级使用上下文；
- 与本批相关的 glossary 子集；
- 输入 SHA256。

### 8.3 `translate-batch`

API 请求要求：

- 使用结构化 JSON 输入输出；
- 禁止 Markdown 和自由解释；
- 只允许返回输入 translation ID；
- 不允许新增、删除或修改 source code；
- 不允许补充原文没有的疾病程度、部位、剂量或病因；
- 数字、单位、缩写和专有名词按 Prompt 规则保留；
- 不确定时返回 `needsReview=true`，不能猜测；
- API key 只从任务专用环境变量读取，绝不写入日志或仓库。

客户端要求：

- Provider 接口与具体 API SDK 解耦；
- 固定 model ID 和 Prompt 版本；
- 支持超时、限速、指数退避和有限重试；
- 已成功批次默认不重新请求；
- 响应先写临时文件，校验后原子替换；
- 缓存键至少包含输入 hash、model ID、Prompt 版本和 glossary hash；
- 任一记录缺失、重复、额外出现或 schema 不合法时整批失败；
- 保存 API 请求元数据和响应 hash，但不保存凭据。

### 8.4 `check-batch`

第二遍检查使用新的、同样受限的小批次：

- 检查漏译、错译、增译；
- 检查同一 glossary 术语是否一致；
- 检查剂量、数值、方法、标本和解剖部位是否被改变；
- 将翻译和复核意见分开保存；
- 有分歧的记录进入人工 review queue。

第二次 API 检查不能替代人工医学审核。

### 8.5 `merge`

优先级固定为：

```text
approved manual override
approved project/source catalog
human-reviewed API translation
machine-checked API translation
machine-draft API translation
source English fallback
```

严格 Release 模式只接受 `approved`。开发预览模式可以显式允许 `machine-checked`，但
Manifest 必须标记为 experimental，不能把机器检查表示为人工批准。

### 8.6 `project`

Projector：

- 深复制来源 Bundle；
- 配合 profile 将 `Claim` 和 `ExplanationOfBenefit` 加入 Synthea FHIR excluded resources，
  从源头停止首期理赔导出；
- 删除首期排除的 Claim/EOB 及仅由它们引用、且删除后不再需要的资源；
- 重新验证引用闭包；
- 只修改 path allowlist 中的 `display`、`text` 或受控模板字段；
- 增加翻译 Release tag；
- 输出 canonical JSON 和 provenance；
- 相同输入、目录和配置必须得到相同 SHA256。

## 9. 翻译分批策略

### 9.1 首个里程碑：当前三病种

当前 corpus 的核心临床术语：

- 30 个 SNOMED code；
- 16 个 LOINC code；
- 4 个 RxNorm code；
- 12 个 CVX code；
- 另有 HL7 状态、角色、分类以及需要清点的受控显示。

顺序：

1. 直接复用 `laboratory-cn` 已覆盖的 16 个 LOINC 中文显示；
2. 翻译 Condition 中的疾病概念；
3. 翻译 Observation/DiagnosticReport 的剩余分类；
4. 翻译 MedicationRequest 药物名称；
5. 翻译 Procedure 和 CarePlan；
6. 翻译 Immunization；
7. 翻译 Encounter、Device、SupplyDelivery 和角色分类；
8. 删除 Claim/EOB，并验证引用闭包；
9. 对 30 个患者 corpus 生成 100% 支持范围 coverage 报告。

### 9.2 第二个里程碑：固定 Synthea 全模块

按术语和领域分批，不按文件逐个翻译：

1. 通用 encounter、wellness、vitals 和 immunization；
2. 常见门诊与感染性疾病；
3. 心血管和代谢疾病；
4. 呼吸、肾脏、神经和免疫疾病；
5. 妇产、生殖和儿科；
6. 肿瘤及复杂心脏手术；
7. 精神、行为健康和 veteran modules；
8. 影像、器械、耗材和其他小型 code system；
9. 受控模板文字；
10. 按 module/domain 建立分层生成矩阵和定向 fixture 验收。

优先翻译去重后的概念目录。禁止在 242 个 module JSON 中逐处写入中文，否则同一代码会
产生多份不一致翻译，且上游升级难以维护。

随机生成不能证明所有罕见分支都被执行。全模块验收由三部分共同组成：静态 module
inventory 保证目录覆盖、定向 fixture 覆盖关键路径、按 module/domain 生成的 corpus
验证真实 exporter 输出。不得用“某次大样本没有发现英文”替代静态覆盖证明。

## 10. Glossary

`glossary.yaml` 是跨批次一致性的约束，不是自由文本提示词。至少维护：

- 常见疾病和症状；
- 解剖部位；
- 检验标本、方法和时间属性；
- 药物剂型、给药途径和频次；
- 手术和护理计划用语；
- 疫苗；
- 医疗角色和机构类型；
- 禁止翻译的缩写、单位、商标和专有名词。

每次 API 调用只注入与本批相关的 glossary 子集。Catalog 中已经存在的批准译名自动加入
translation memory，后续批次不得为同一 code 重新生成随机译名。

## 11. 验证与测试

### 11.1 Catalog 验证

- translation ID 唯一；
- `sourceSystem + sourceCode` 唯一或有显式 designation；
- 中文显示非空；
- 需要中文的记录至少包含一个中文字符；
- source code 和 source display 与 inventory 一致；
- 不允许未知 review status；
- `approved` 必须满足批准来源要求；
- glossary 冲突失败；
- API 结果不得静默覆盖人工 override。

### 11.2 Bundle 不变量

中文化前后必须保持：

- 非 Claim/EOB 资源 ID；
- 所有 `Coding.system/version/code`；
- 日期、时间、状态 code；
- Observation 数值；
- Quantity 数值和 UCUM code；
- 剂量数值和频次 code；
- 非排除资源的引用闭包；
- Patient、Practitioner 和 Organization 的既有中国身份合同。

允许改变：

- allowlist 中的 `Coding.display`；
- allowlist 中的 `CodeableConcept.text`；
- 审核过的受控模板文字；
- Bundle translation tag；
- Claim/EOB 及删除它们后明确判定为无用的资源。

### 11.3 Coverage

Coverage 不能通过扫描所有英文字符计算。FHIR URL、标准代码、ID、缩写和单位本来就可以
是英文。Coverage 以 inventory 中标记为 `DISPLAY_LOOKUP`、`UI_LABEL` 或
`TEMPLATE_LOOKUP` 的记录为分母，至少报告：

- 总记录数；
- approved、human-reviewed、machine-checked、machine-draft 数量；
- 缺失和冲突数量；
- 按 code system、domain、resource type 和 module 的覆盖率；
- 输出 corpus 中实际命中的覆盖率；
- fallback 到英文的次数。

### 11.4 CI

CI 不访问翻译 API。CI 只使用提交的 catalog、glossary、mock API 响应和合成 fixture：

- Ruff、mypy、pytest；
- schema validation；
- batch determinism；
- response fail-closed tests；
- projector path allowlist tests；
- FHIR parser 和 reference closure；
- clinical invariants；
- 当前 corpus coverage gate；
- 上游 inventory diff gate。

API 翻译是显式的维护者任务。模型不可用、限速或结果变化不能影响普通 CI 和运行时。

## 12. Release 与升级

翻译 Release 至少固定：

- Synthea commit；
- 支持的 profile ID/hash；
- inventory hash；
- catalog hash；
- glossary hash；
- Prompt 版本；
- API model provenance；
- review policy；
- compiler version/commit；
- coverage 和 validation hash。

升级 Synthea 时：

1. 对新 commit 重新生成 inventory；
2. 比较新增、删除和来源显示变化；
3. 复用未变化代码的批准译名；
4. 只为新增或冲突记录创建 API batch；
5. 重新运行全模块 corpus；
6. 发布新的翻译 Release，不覆盖旧 Release。

## 13. 开发任务卡

以下任务按依赖顺序分派。每个 Agent 只完成一张任务卡，避免一轮同时设计 schema、调用
API、改 FHIR 和生成全部翻译。

### T1：Inventory 与字段分类

目标：建立固定 Synthea commit 的完整、可重复清单。

交付：

- `inventory.py`；
- CLI `synthea translation inventory`；
- module JSON parser；
- corpus FHIR path collector；
- exporter 内置显示发现策略；
- path classification registry；
- inventory、conflict 和 baseline coverage fixture。

验收：

- 重复执行字节一致；
- 得到已知的 242 module baseline；
- 识别 2,149 个 module terminology key；
- Claim/EOB 标记为 EXCLUDE；
- 不修改任何 Bundle 或 module。

### T2：Translation Schema、Catalog 与 Glossary

目标：定义翻译数据合同和不可变 Release。

交付：

- translation record/release JSON Schema；
- catalog/glossary loader；
- review status 和 override precedence；
- Manifest 和 hash 规则；
- schema、重复、冲突和 fail-closed 测试。

验收：

- 无效、重复或冲突记录构建失败；
- API 草稿无法伪装成 approved；
- `laboratory-cn` 可以投影成合法翻译记录。

### T3：API Batch Pipeline

目标：实现小上下文、可恢复、可审计的翻译与复核流程。

交付：

- `batches.py` 和 `api.py`；
- make/translate/check/merge CLI；
- Provider Protocol；
- Prompt 模板和版本；
- 结构化请求响应 schema；
- cache、resume、retry、rate limit 和 atomic output；
- mock provider tests。

验收：

- CI 不访问网络；
- 丢记录、多记录、改 code、非法 JSON 时整批失败；
- 完成批次可重复执行而不再次计费；
- API key 不出现在文件、错误或日志中。

### T4：FHIR Display Projector

目标：将翻译目录安全应用到 FHIR R4 Bundle。

交付：

- `projector.py`；
- resource/path allowlist；
- CodeableConcept 和 Coding display 处理；
- profile 的 Claim/EOB exporter exclusion；
- Claim/EOB 排除及孤立资源处理；
- translation tag 和 provenance；
- deterministic writer。

验收：

- 只改变允许字段；
- system/version/code、日期、数值和单位不变；
- 删除 Claim/EOB 后引用闭合；
- 缺翻译时保留英文并报告，不调用 API。

### T5：Validation 与 Coverage

目标：建立不能被“看起来是中文”绕过的验收门槛。

交付：

- `validation.py`；
- catalog、FHIR、不变量和 coverage 报告；
- 30 人 corpus 验证；
- CI coverage gate。

验收：

- 任一临床 code、数值、单位或引用改变时失败；
- coverage 分母来自字段分类清单；
- 报告区分 approved 与 machine-only 翻译。

### T6：当前三病种翻译目录

目标：完成首个可演示的完整中文纵向病历。

交付：

- 复用 16 个 `laboratory-cn` LOINC 中文显示；
- SNOMED、RxNorm、CVX 和辅助受控术语的小批次翻译；
- glossary；
- review queue 和必要的人工 overrides；
- 首个 translation Candidate。

验收：

- 当前支持范围的实际 corpus display coverage 为 100%；
- Claim/EOB 不输出；
- 没有未记录的英文 fallback；
- 30 个 Patient 全部通过临床不变量和引用验证。

### T7：固定 Synthea 全模块翻译

目标：扩展到固定 commit 的所有支持模块。

交付：

- 按领域生成和复核的 batch；
- 增量 catalog；
- 静态 inventory、定向 fixture 和按 module/domain 生成的测试 corpus；
- domain/module coverage 报告；
- 冲突和未支持资源清单。

验收：

- 所有支持 module 的受控显示都有目录记录；
- 所有排除和 defer 项均机器可读；
- 不依赖随机样本遍历所有罕见分支；
- 新模块或新 code 会触发 coverage gap，而不是静默输出未审查文字。

### T8：发布、文档和升级演练

目标：使其他开发者可以离线复现和维护。

交付：

- Candidate build 和 Manifest；
- 操作手册；
- API 翻译维护手册；
- reviewer 手册；
- Synthea commit 升级 diff 演练；
- CI 与发布检查。

验收：

- 普通开发、测试和运行完全离线；
- 新机器只使用已发布目录即可生成相同中文 Bundle；
- 旧翻译 Release 不因模型、Prompt 或上游变化而改变。

## 14. 并行与所有权

T1 和 T2 的数据合同确定后：

- T3 API pipeline 与 T4 FHIR projector 可以并行；
- T5 在 T2/T4 接口稳定后开始；
- T6 依赖 T1、T2、T3、T4 和 T5；
- T7 只能在 T6 达标后扩展；
- T8 最后进行。

建议所有权：

| 角色 | 职责 |
|---|---|
| Inventory owner | 上游模块、exporter 和 FHIR 路径清单 |
| Translation pipeline owner | API batch、缓存、Prompt 和 provenance |
| FHIR owner | projector、合法性和临床不变量 |
| Terminology reviewer | 译名、glossary、冲突和人工 override |
| Release owner | coverage gate、Manifest、rights 和发布 |

Agent 可以实现代码、生成翻译草稿和发现候选错误，但不得自行把机器翻译标记为人工批准。

## 15. 风险与控制

| 风险 | 控制 |
|---|---|
| 大上下文导致漏译或幻觉 | 去重后每批 20 至 40 条，按领域分组 |
| 同一术语多种译名 | code-keyed catalog、glossary、translation memory |
| API 改动代码或剂量 | 结构化输出、字段白名单、整批 fail closed |
| API 中断或重复计费 | cache、resume、稳定 batch ID、完成批次不重跑 |
| 模型升级导致旧结果变化 | 固定 model/prompt，发布后只读，不自动重译 |
| FHIR 被递归字符串替换破坏 | resource/path allowlist 和临床不变量测试 |
| “全中文”掩盖未审核内容 | coverage 按 review status 分层报告 |
| 上游新增代码未被发现 | inventory diff 和 CI coverage gate |
| 向 API 发送不必要数据 | 只发送去重术语和非患者上下文 |
| 第三方术语权利不明确 | Release 前执行 source terms 和分发权限检查 |

## 16. Definition of Done

### Milestone A：当前三病种完整中文显示

- 当前 corpus 支持范围内的临床名称、药品、检验、操作、疫苗、护理计划、就诊分类和
  器械名称都有中文显示；
- Patient、Practitioner、Organization 保持现有中国身份合同；
- Claim/EOB 不输出；
- FHIR 字段名、code、日期、数值、单位和引用保持不变；
- 支持范围实际命中 coverage 为 100%；
- 输出包含翻译 Release provenance；
- 运行时不访问 API；
- 30 人 corpus 全部通过。

### Milestone B：固定 Synthea 全模块完整中文显示

- 固定 commit 的 242 个 module 已进入 inventory；
- 所有支持资源和路径均有明确处理策略；
- 受控显示达到 100% catalog coverage；
- 自由文本、理赔和模型本地化继续明确排除或 defer；
- 全模块 corpus、FHIR 和临床不变量验证通过；
- 新 Synthea commit 可以通过 inventory diff 增量维护。

达到 Milestone B 表示固定版本的 Synthea 可以生成完整、可追溯的中文显示病历；它不表示
Synthea 已经模拟中国疾病流行病学、中国诊疗路径或中国医保理赔。
