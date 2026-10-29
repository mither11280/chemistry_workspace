# A2 教学分类 1.1 扩展

分类标识 `chemistry-workspace-a2-teaching12-1.1.0`；仍是原来 12 个稳定章节 ID，AS 的 19 章不变。兼容读取原 A2 `1.0.0` 判断。PDF 坐标 schema 和题库代际不变，不重新编号或清空作业。

第 11 章的显示名称改为「有机合成与方法 / Organic synthesis (multi-step and selected single-step methods)」。教师在 2026-10-29 明确确认以下扩展：

- 原来的综合、多步路线推断继续归 11。
- 单步臭氧化、Diels–Alder／环加成可以归 11，记录单步方法标签。
- 有机手性碳、光学／几何立体异构、对映异构和外消旋等归 11。
- 配合物的顺反／光学异构仍归 6，不因“stereoisomer”关键词挪到 11。
- 普通醛／酮还原为醇归 11。酰胺相关反应归 9；实际底物和解题要求决定分类，不能看到 NaBH4／LiAlH4 就统一分类。
- 教师随后确认：没有更明确 A2 主题的其余基础有机内容，包括普通烯烃加成／氧化、卤代烃反应、普通羧酸／酯反应、官能团检验、简单有机命名和结构式，也归 11，分别记录方法标签。真正考查苯类、酰氯、胺酰胺、聚合物或仪器分析的任务仍按相应章节。
- Paper 4 的考试身份和教学课程均保留 A2，不转入 AS。
- 若杂化计数的对象含苯环，归 7；普通结构式或分子式计数不因苯环只是背景而自动增加芳香反应依赖。
- 基础氧化还原配平和滴定计量归 3；沉淀滴定也按计量任务收纳，但不误标为氧化还原反应。VSEPR 形状题归 6。
- `cie-9701-m19-42-q1-a` 只问氮氧化物来源，按教师的暂定偏好收纳于 9。它是明确标记的教学收纳例外，不是胺／酰胺化学依赖；实际知识标签保留 `environment.nitrogen-oxides`，可日后调整，不推广为所有含氮环境题的规则。

必要前问仍参与主章节闭包；若本问实际还要求更靠后的知识，继续取最大章号。题面把手性当背景、实际只要求 NMR 峰数的问仍归 12。反过来，独立问手性碳的题不能因为同大题稍后出现 NMR 就归 12。

第二批落实了 78 个基础有机／芳香杂化判断、2 个碘仿问、14 个基础无机问和上述 1 个暂定收纳例外。原卷材料核查与分类判断分开记录；分类确认不能使有裁切或评分异常的题直接通过。

## 标签和决定记录

`metadata.knowledge_tags` 与唯一的 `primary_chapter` 独立，例如：

```json
{
  "knowledge_tags_version": "chemistry-workspace-knowledge-tags-1.0.0",
  "knowledge_tags": ["organic.ozonolysis", "synthesis.single-step"]
}
```

本批使用有机方法／结构标签，以及 `structure.aromatic-hybridisation`、`structure.vsepr`、`redox.equation-balancing`、`calculation.titration` 等。标签须有解题依据，不从名称或偶然出现的词自动推出。定义题、手性碳计数等不误标为“单步反应”。没有这个字段表示还没有整理标签，不表示没有知识依赖。字段对由公开 Question Index Schema 校验；标签名使用小写命名空间，可为后续实验能力和细分知识保留扩展。

标签整理仍限于已有明确判断的单位（包括因材料异常待整理的单位）。还没有全库填充多维标签，也没有完成相应 UI 联合检索；不能以这些标签代替全库细分检索验收。

分类变更保留 `classification_history`、政策 ID、原始材料指纹及变更前的教学判断指纹。改变材料后旧决定无效；仅改变课程归属也要记录为何新规则适用于这道实际小问。

公开决定记录：[臭氧化／环加成](single-step-scope.json)、[立体异构／羰基还原](organic-teaching-repairs.json)、[基础有机／芳香杂化](foundation-teaching-repairs.json)、[基础无机](inorganic-teaching-repairs.json)、[碘仿](iodoform-teaching-repairs.json)、[暂定氮氧化物收纳](nitrogen-teaching-repairs.json)。课程决定都不能越过材料 QA 或来源完整性门禁。

Paper 5 已确认采用独立的实验技能分类（Planning、Data Processing、Graphical Analysis、Evaluation），在有依据时附加化学章节标签。此决定尚不表示 Paper 5 已切分、验收或发布。
