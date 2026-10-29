# A2 Paper 4 教学分类规范

本页保留 v0.5.1 的 1.0 规范。主分支的新课程决定见[分类 1.1 扩展](../reliability/classification-1.1.md)，其中第 11 章的范围已按教师确认扩展；旧索引仍兼容读取。

分类体系标识：`chemistry-workspace-a2-teaching12-1.0.0`。本规范是教师的教学顺序，并非 Cambridge 官方考纲条目编号。AS 继续使用 `chemistry-workspace-teaching19-1.0.0` 和 `ch01`–`ch19`，A2 使用 `a2-ch01`–`a2-ch12`；两者的相同章号不表示相同课程内容。

| 学科组 | ID | 章节 |
| --- | --- | --- |
| Physical chemistry | a2-ch01 | Chemical energetics (lattice energy + Group 2 hydration and solution) |
| Physical chemistry | a2-ch02 | Entropy & Gibbs free energy |
| Physical chemistry | a2-ch03 | Electrochemistry |
| Physical chemistry | a2-ch04 | Equilibria |
| Physical chemistry | a2-ch05 | Reaction kinetics |
| Inorganic chemistry | a2-ch06 | Chemistry of transition elements |
| Organic chemistry | a2-ch07 | Benzene (benzene reactions + phenol + phenylamine) |
| Organic chemistry | a2-ch08 | Carboxylic acids derivatives (acyl chloride) |
| Organic chemistry | a2-ch09 | Amine and amides |
| Organic chemistry | a2-ch10 | Polymers |
| Organic chemistry | a2-ch11 | Organic synthesis (multi-step) |
| Analysis | a2-ch12 | Analytical techniques (NMR + Chromatography) |

## 主章节

`metadata.teaching.required_chapters` 记录完成当前小问真正需要的 A2 章节。依赖闭包中所有章节的最大编号为唯一 `primary_chapter`，并且 `topics` 恰为该章的一个 ID。已给出的反应式、背景故事、化合物名称、图中不参与解题的官能团不独立增加章节依赖。

苯胺自身的特征反应归 7；脂肪胺和酰胺归 9；比较两者则需要 7 和 9。给定路线中单独一道已知转化的试剂、产物或机理按实际转化分类；需要补全连续中间体、多个步骤或设计新路线才使用 11。无机反应机理中的“two steps”和能量循环中的“two steps”不属于有机合成。

12 包括 Paper 4 实际考查的 NMR、色谱、IR、质谱等分析内容，也用于旧卷的电泳分离。用已给结构计算谱峰不要求先完成其无关的合成路线。Cl/Br 同位素谱型在 A2 分析题中可记录 AS 同位素基础，并归入实际服务的分析主题；AS 的原子结构特殊边界保持不变。

配合物稳定常数 Kstab（包括表达式、单位、计算、比较稳定性和相关配位平衡）统一归入第 6 章 Chemistry of transition elements，而非仅因涉及平衡常数归第 4 章。名称在背景中出现而实际只问熵、自由能等其他内容时，仍按实际解题要求分类。

纯 AS 小问在有明确联系时按其服务的 A2 主题组织，判定依据须说明这项基础关系。没有可靠 A2 联系的独立 AS 任务进入待整理区；不能仅凭相邻题的章号赋值。

## 独立小问与答案

稳定 ID 示例：`cie-9701-m25-42-q2-c-i`；考试身份来自原卷，不由课程章节改变。保留 `(i)`、`(ii)` 的精确区别、独立官方分值、自己的区域和不含答案的共用上下文。需要前问结果的小问列入 `prerequisites`；作业按依赖顺序补入并仅计分一次。共用上下文按源 ID 和上下文键去重。

少数原卷整题只有一个未标字母的计分任务（例如原卷 Q9），使用 `...-q9-unit` 和空 `part_path`，原题标签仍为 `9`。如果该整题的官方 MS 唯一行印为 `9(a)`，记录 `official_answer_label: "9(a)"`，并核对唯一对应关系及分值。不得给原卷伪造 `(a)` 标签。其他官方标签矛盾、缺分或边界不明确的情况保留具体疑点，不能通过此字段随意改配答案。

官方 MS 的完整紧凑标号 `4b(ii)` 在表格定位时规范化为 `4(b)(ii)`；公开题号解析仍采用严格的带括号格式。这只识别明确印出的父题、字母和罗马数字，不补猜缺失小问。每个标号单独划定答案行并核对分数，避免将其并入前一问。原 PDF 及其印刷标号保持原样。

## 可验证依据

公开索引保留解题理由和材料指纹；原文提取和批次阅读材料仅存维护者的本地目录。指纹包含原 QP/MS 哈希、原题标签及所有题目、共用上下文和答案区域。改变材料后必须重新读取判定，或证明只移除了外围空白。关键词建议只显示候选，不使题目变为可用。

相同内容的变体复用判定时，必须同时匹配题干、共用上下文、官方 MS、分值和每一个区域的渲染哈希，并核对依赖闭包；只相同题目文字不足以证明结构式和表格相同。复用证据保留原始身份和哈希，不复制或改写官方答案。

## 运行与升级

含 A2 的更新包最低读取版本为 0.5.1。题库代际不变，因此保留 AS ID、个人作业、草稿、备注和 CIE2。新 App 仅自动退役经过精确内容哈希确认的 v0.5.0 基础／完整包激活指针；迁移前备份公共索引、可重建查询数据库及局部校准。个人作业数据库不参与清空或迁移。

自定义激活版本保留并提示冲突。指针切换失败或进程中断会恢复旧激活和查询数据库；重复启动不重复执行已完成的升级。完整包与增量资料包可以描述同一个 v0.5.1 目标，重复安装仅补充经过校验的缺失原文件，不重复迁移个人状态。
