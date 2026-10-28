# 19 章教学题库扩展（v0.5）

这份扩展沿用 `question-index.schema.json` 的 1.0.0 PDF 坐标系统。题库代际为
`cie-9701-as-teaching19-v1`，分类体系为 `chemistry-workspace-teaching19-1.0.0`。
代际、分类版本、坐标 schema 版本是三个不同概念，不能互相替代。

## 主章节

每个正式选题单位只属于一个主章节。`required_chapters` 记录本问本身需要的章节；
`primary_chapter` 为本问和全部必要前问所需章节的最大编号。背景名称、干扰项以及
题面已经提供而不要求回忆的反应，不单独形成后续章节依赖。

1. Atomic structure
2. Atoms, molecules and stoichiometry
3. Chemical bonding
4. States of matter
5. Chemical energetics
6. Redox
7. Equilibria
8. Reaction kinetics
9. The Periodic Table: chemical periodicity
10. Group 2
11. Group 17
12. Nitrogen and sulfur and other inorganic tests
13. An introduction to AS Level organic chemistry
14. Hydrocarbons + Polymerisation
15. Halogen compounds
16. Hydroxy compounds
17. Carboxylic acids and derivatives (with nitrile)
18. Carbonyl compounds (aldehydes and ketones) and organic functional group tests
19. Analytical techniques

红外、M+1 碳数及 fragmentation 归 19；相对原子质量、Cl/Br 同位素谱型本身归 1。
有机官能团鉴定归 18，无机鉴定归 12；同时有更后章节要求时仍取最大值。
章节是自定义教学顺序，不冒充某一版本官方 syllabus 的 statement 编号。
原卷 syllabus 来源与当前教学映射分别保留在 metadata 中。

## 可移植字段

所有字段位于 `metadata.teaching`，结构由 JSON Schema 检查，引用关系及章节闭包由
`bank.teaching.taxonomy.validate_teaching` 检查。

| 字段 | 含义 |
| --- | --- |
| taxonomy_id | 上述固定版本标识 |
| status | `ready` 或 `pending`；只有 ready 参与自动选题 |
| primary_chapter | ready 时为 1–19，pending 时为 null |
| required_chapters | 本问所需章节，递增、唯一 |
| parent_question_id | 来源大题身份；不是另一个可选计分单位 |
| part_path | 如 `["a", "ii"]`；Paper 1 为 `[]` |
| source_order | 来源大题内从 0 开始的叶子顺序 |
| prerequisites | 必须连带的其他独立计分小问 ID，无循环 |
| contexts | `{key, regions}` 数组，保存必要共用题干和图表 |
| own_regions | 本问内容与答题空间的原始坐标 |
| evidence | `{method, reason}` 分类依据；自动结构检查不等于人工独立复核 |
| issues | 待整理原因代码数组 |

`question.regions` 必须严格等于 contexts 依次展开后再连接 own_regions。
所有区域使用原坐标规范的 PDF point、从 0 开始的页码和未旋转 CropBox 坐标。
共用上下文 key 在同一来源中代表相同区域；不同题不得用相同 key 指向不同图形。
答案使用独立 MS source_id 和精确小问区域，绝不能按题号整数前缀将 `(i)` 匹配到 `(ii)`。

同一作业先求 prerequisites 闭包，将必要前问放在依赖问之前，每个 ID 只计分一次；
学生卷按来源 source_id 与 context key 去重共用上下文，答案卷只按最终小问顺序输出。
前问答案不会作为学生卷上下文。原始题号为字符串，如 `2(a)(ii)`，新版 ID 如
`cie-9701-m24-22-q2-a-ii`；既有 Paper 1 ID 保持稳定。

pending 题可缺少尚未确定的答案区域，不能借此变成正式可选题；普通题的非空区域要求
不变。待整理不属于第 20 章，JSON/CSV 保留身份、坐标、候选章节及问题。

## 生产与复现

`rebuild_teaching_bank.py` 从原卷生成候选边界和分值，不决定正式分类。
`teaching_decisions.py list/show` 展示候选，`approve` 记录明确的分类依据；
`apply_teaching_decisions.py` 将判断应用到坐标索引。关键词只用于提示。

判断绑定 QP/MS 的 SHA-256、原题标签及全部题目/答案区域，包括共用图形。
变更原卷或坐标会使判断失效，必须重新核对；不能只改 fingerprint 来绕过核对。
私有候选中的原题全文留在忽略的 data 目录，公开索引只含位置和编者元数据。

```sh
python scripts/apply_teaching_decisions.py --workdir data/teaching19 \
  --decisions data/teaching19-decisions.json --output data/teaching19-current
python scripts/verify_teaching_bank.py --help
```

## 个人数据与恢复

首次启用新代际时，程序在写新作业前将整个旧 data 目录原样移到
`generation-archives/<archive-id>/data`，包含旧作业、草稿、局部校准、SQLite 和激活信息。
原始 sources 文件保留不动。切换使用锁和事务日志；失败时恢复旧目录。
初始化标记确保重复启动不会再次清空新版作业。

关闭 App 后可用 `scripts/restore_teaching_archive.py --help` 查看恢复工具。
恢复旧档案前，新版个人数据同样归档保存。恢复后使用与旧题库匹配的旧版 App；
再次开启新版 App 会重新进入代际切换。不要在 App 运行时手动移动目录。

新版分享使用 CIE2 并带代际；CIE1 必须使用旧版题库，不静默转换。
新代际完整包与旧版普通增量包不同；不能让旧 ID 必须保留规则将旧大题重新带回活动题库。

跨字母小问的定义可通过 `indexes/teaching19-context-overrides.json` 明确补充。
该制作文件只引用同一大题已经测量的 introduction key，附带补充理由；不能引用计分小问
本体或答案。比如 `(c)` 定义的 A/B/C 及碳数约束可补给 `(d)` 的鉴定表。
最终公开 question.regions 和 contexts 已包含这些区域，第三方阅读器无需理解制作文件。
此类修正先于 material fingerprint 计算；已发布判断仍按完整材料变更规则失效。

待整理记录可含 `candidate_chapters`（1–19 的唯一整数数组），用于检索提示。
它来自宽泛候选规则与已有判断的并集，不是正式分类依据，不参与章节过滤、主章节计算
或自动组卷。`required_chapters` 与 evidence 才记录明确的解题要求判断。

第 13 章的基础范围包含官能团识别、各类有机物命名/通式、结构式读写、异构、杂化，
以及 addition/substitution/elimination/hydrolysis/condensation 和 oxidation/reduction
等反应术语。这与已登记 2025–2027 syllabus 的 13.1–13.4 相对应。
因此完整给出反应前后结构、只问通用反应类型或氧化/还原角色时，可以归 13；
若还要预测产物、选择特征试剂/条件、补全具体反应机理，则保留所需后续章节。
单纯提供某个化学品名称不代表需要掌握该章的反应。

## 完整离线资料包

v0.5 App 和源码下载内的公共索引属于同一新代际。完整 `.qbank` 以该索引 revision 为基础，
包含相同题目及全部已登记原卷，将 revision 推进为 `<index revision>.assets.1`。
这允许源码安装用户一次补齐 PDF，也允许 App 用户按原有更新流程校验和安装资料。
普通更新仍禁止换代和删除稳定 ID；旧版用户必须先安装 v0.5 App，不能直接用资料包代替换代。

维护者可运行 `scripts/build_teaching_bundle.py --help`。打包工具要求完整 source_id 路径映射、
明确再分发声明及逐文件哈希授权清单，缺一份原卷也不称为完整资料包。
程序仓库只提交规范、坐标与分类元数据；原卷只进入已获授权的 Release 附件。

## 本版切分核对

小问分值从各自 QP 末尾标分与 MS 分值栏分别读取；大题合计也要对账。
`(i)`、`(ii)` 必须完整匹配。旧 PDF 嵌入字体可能把标签拆成相邻文本片段，
只连接接触的标签片段；打印错误或无法唯一对应的标签作为边界，不能并入前问答案。
单独 Total 汇总行不重复计分，而 `total electrons` 等真实评分行仍须计分。

印在前问分值之后的未计分说明（包括以字母化合物名称开头的说明）转为后问共用上下文；
明确属于当前小问的附录不移走。`Give your answer to one decimal place` 不是前问引用；
一个自足任务内部的 `and hence calculate` 也不自动连带前一小问。

相同内容变体只允许在 Paper 1 的 task 文本及所有区域渲染尺寸、像素完全一致且来源哈希
已核对时复用分类依据，仍绑定目标卷自己的材料 fingerprint。不得据相同题号、相似关键词
或相同文字但不同图形直接复用；不复用答案身份、坐标、问题状态和依赖关系。
`scripts/reuse_teaching_decisions.py` 提供可选证明记录，不是语义分类器。

公开制作依据在 `indexes/teaching19-decisions.json`，只含编者判断和材料指纹。
重建候选需要维护者提供 `source_id -> 本地 PDF 路径` 映射；私有全文候选不提交。

```sh
python scripts/rebuild_teaching_bank.py --sources /path/to/source-map.json --output data/candidates
python scripts/apply_teaching_decisions.py --workdir data/candidates \
  --decisions indexes/teaching19-decisions.json --output data/reproduced
```

源码快照已包含所有最终坐标，不需要运行制作流程即可使用；只须导入对应原卷。
