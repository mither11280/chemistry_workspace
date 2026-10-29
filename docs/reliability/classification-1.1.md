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

必要前问仍参与主章节闭包；若本问实际还要求更靠后的知识，继续取最大章号。题面把手性当背景、实际只要求 NMR 峰数的问仍归 12。反过来，独立问手性碳的题不能因为同大题稍后出现 NMR 就归 12。

本检查点先落实了臭氧化／环加成与立体异构／羰基还原两批；其余基础有机的新规则已经确认，具体题目继续核对，不把课程规则确认等同于所有材料已通过。基础无机等尚未确认的内容不能因此自动变成 11。

## 标签和决定记录

`metadata.knowledge_tags` 与唯一的 `primary_chapter` 独立，例如：

```json
{
  "knowledge_tags_version": "chemistry-workspace-knowledge-tags-1.0.0",
  "knowledge_tags": ["organic.ozonolysis", "synthesis.single-step"]
}
```

本批使用 `organic.ozonolysis`、`organic.diels-alder`、`synthesis.single-step`、`organic.stereochemistry`、`organic.carbonyl-reduction`。标签须有解题依据，不从名称或偶然出现的词自动推出。定义题、手性碳计数等不误标为“单步反应”。没有这个字段表示还没有整理标签，不表示没有知识依赖。字段对由公开 Question Index Schema 校验；标签名使用小写命名空间，可为后续实验能力和细分知识保留扩展。

目前 54 个本批处理单位有这些标签（包括仍因材料异常待整理的单位）。还没有全库填充多维标签，也没有完成相应 UI 联合检索；它属于后续工作，不能以本批 54 个标签代替全库细分检索验收。

分类变更保留 `classification_history`、政策 ID、原始材料指纹及变更前的教学判断指纹。改变材料后旧决定无效；仅改变课程归属也要记录为何新规则适用于这道实际小问。

公开决定记录：[臭氧化／环加成](single-step-scope.json)、[立体异构／羰基还原](organic-teaching-repairs.json)。这两类课程决定都不能越过材料 QA 或来源完整性门禁。
