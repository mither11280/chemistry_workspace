# 题间 · Chemistry Workspace

面向 A-Level 化学教师的本地组卷软件。支持离线题库检索、按描述选题、手动调整作业、学生卷／Mark Scheme PDF、个人作业和组卷代码分享。

**主分支正在开发 v0.6。** 两批源资料与分类修复使可用单位从 7,666 增至 7,757、待整理从 332 减至 241；稳定 ID 和原卷哈希保留。新的 A2 分类规则及实测、剩余问题见[可靠性检查点](docs/reliability/README.md)。这不是新安装包已经发布；当前稳定下载仍为 v0.5.1，Paper 5 和教师工作流改进继续开发。

**v0.5.1：新增 A2 Paper 4 与外围留白修正。** 本地登记的 2018–2026 年 60 对 Paper 4 QP/MS，从 510 道大题拆出 3,541 个计分小问，3,277 个可用、264 个待整理。保留 AS 的 4,457 个稳定题目 ID、个人作业和 CIE2 分享兼容。整库共 7,998 个单位，7,666 个可用。详见 [Paper 4 覆盖报告](docs/paper4/coverage.md) 与 [分类规范](docs/paper4/classification.md)。

## 下载与使用

[macOS Apple Silicon 安装包与完整题库包](https://github.com/mither11280/chemistry_workspace/releases/tag/internal-v0.5.1)。将「题间.app」拖入 Applications 即可运行，无需另装 Python。完整 App 包含 352 份已登记的 QP、MS、考纲和 2016 Data Booklet，首次启动自动导入并检查哈希。发布前请以 GitHub 上实际可下载的 Release 为准。

此版本是 ad-hoc 签名、未经 Apple 公证的内部测试包，文件名含 `INTERNAL-UNNOTARIZED`；macOS 可能要求在系统设置中允许首次打开。构建、公证和运行环境说明见 [macOS 分发](docs/macos-distribution.md)。

日常流程：选择章节或输入条件 → 添加小问 → 为作业命名、调整题序和备注 → 导出学生卷与答案。必要前问自动加入，每问只计分一次；共用题干和图表合并输出。分享代码可在同代际题库导入，再继续增删修改。

## AS／A2 教学规则

AS 使用原 19 章；A2 Paper 4 使用独立的 12 章，按 Physical／Inorganic／Organic／Analysis 展示。切换课程保留已选题，可混合组卷。Kstab 表达式、单位、计算和稳定性比较统一归 A2 第 6 章 Transition elements；真正需要更后章节时仍按最高编号。主分支的[分类 1.1](docs/reliability/classification-1.1.md) 扩展第 11 章，收录已确认的单步臭氧化／环加成、有机立体异构和普通醛酮还原；配合物异构仍归第 6 章。

界面按 Physical／Inorganic／Organic chemistry 展示 19 章。每个选题单位只有一个主章节：**本问及必要前问真正需要的章节中，编号最大的一章**。背景名称和干扰选项不单独增加章节要求。

红外、fragmentation、M+1 碳原子数归第 19 章；相对原子质量和 Cl/Br 同位素谱型本身归第 1 章。有机官能团检验归第 18 章，无机鉴定归第 12 章。完整给出反应结构、仅要求通用反应术语时可归第 13 章；预测产物、选择试剂或机理保留相应后续章节。完整顺序与可移植字段见 [分类规范](docs/teaching19-format.md)。

Paper 2 按最小独立计分小问选择，保留原标签、必要答题空间、跨页图表及官方 MS。待整理区独立于 19 章，可预览并下载 [JSON](docs/teaching19/pending.json)／[CSV](docs/teaching19/pending.csv)，不参与章节自动组卷。

分类依据由制作代理读取题干、上下文和评分内容后记录。结构检测、分数对账和抽查不等于独立人工逐题复核，不承诺未经测量的准确率。

## 升级与个人作业

**从 v0.5.0 更新至 v0.5.1 不清空作业。** 直接替换 App；已知 v0.5.0 基础／完整包的旧激活索引会在备份后升级，人工校准保留。未知自定义题库继续保留并显示版本冲突。更新资料可安装兼容更新包；全新安装或缺少旧资料时选择完整题库包。新资料包最低要求 App v0.5.1。

从 v0.4 或更早版本首次进入 v0.5 时，使用新的题库代际 `cie-9701-as-teaching19-v1`：程序先将旧个人数据库、草稿、局部校准和题库激活信息整体归档，新代际个人作业从空白开始。旧作业不转换，重复启动或重装不会再次清空新版作业。原始 PDF 保留。

独立 App 数据在 `~/Library/Application Support/ChemistryWorkspace`；开发版默认使用工程目录。新分享代码为 `CIE2.`，携带题库代际；旧 `CIE1.` 代码提示使用旧版题库。

恢复旧作业时先退出 App，使用源码中的工具，并换回旧版 App：

```sh
python scripts/restore_teaching_archive.py --home "/path/to/ChemistryWorkspace" ARCHIVE_ID
```

归档 ID 对应用户目录的 `generation-archives/` 子目录。恢复前新版个人数据也会归档。切换失败自动恢复旧目录。[完整恢复说明](docs/teaching19-format.md#个人数据与恢复)。

## 从源码运行与导入原卷

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/server.py
```

Git 仓库包含程序、规范、坐标、分类依据和测试，**不包含 Cambridge PDF、缓存或个人数据**。缺少 PDF 时可浏览题目元数据，预览／导出提示导入对应文件。

可以在 App「导入原卷」批量选择合法取得的 QP/MS；程序根据文件名、SHA-256 与页面几何关联。也可以在新版 App「题库版本与更新」导入本版本的完整 `.qbank` 附件，一次补齐全部登记资料。先安装 v0.5.1 App，再安装相应资料包；旧版不能直接用该包换代。早年 Paper 4 所需 Data Booklet 可单独下载复用，不会在每份作业中重复附加 20 页。程序不从第三方网站自动下载试卷。

## 存储与公开格式

- `indexes/question-index.json`、`source-manifest.json`：当前题库的可移植标准数据源。
- `indexes/teaching19-decisions.json`：绑定原卷哈希与全部区域的明确分类依据。
- `indexes/releases/`：历史坐标快照；旧大题不进入新版活动题库。
- `schemas/`、`examples/`、`docs/`：JSON Schema、原创示例、坐标与分类规范。
- `app/bank/teaching/`：分类契约、小问切分、依赖闭包与代际归档恢复。
- `app/bank/catalog.py`、`sources.py`、`render.py`：SQLite/FTS、本机原卷关联、WebP 与矢量组卷。
- `sources/`、`data/`、`exports/`：本机原卷、个人状态、缓存与输出，全部默认排除 Git。

每份 QP/MS 保存一份不可变原始 PDF；不预先生成每题 PDF。坐标使用 PDF point，page_index 从 0 开始，原点是未旋转 CropBox 左上角，独立于显示器和预览尺寸。跨页通过多个 regions 表达。[公开坐标规范](docs/question-index-format.md) 可由第三方独立实现。

正式 PDF 直接引用原卷矢量内容，按作业顺序编号，附原题号与 `.mapping.json`，答案顺序一致。原卷本身的位图保持原样。PDF clip 不是内容脱敏，可能保留可见区域以外的页面资源。WebP 仅作可删除缓存，默认限额 128 MiB，不影响导出。

## 验证与维护

```sh
python scripts/bank_tool.py validate
python -m unittest discover -s tests -v
node --check app/app.js
node --check app/prompt.js
```

测试使用原创 PDF；可选 `CIE_CORPUS` 开启本机授权样本回归。实际样本的接口验收、存储／预览／20 题导出实测见 [v0.5 验收与性能](docs/teaching19/validation.md)。

维护者从原卷重建候选后，使用 `teaching_decisions.py list/show/approve` 记录判断，再 `apply_teaching_decisions.py` 应用。关键词只生成候选；坐标或原卷变更使原判断失效。完整复现流程见 [生产规范](docs/teaching19-format.md#生产与复现)。无可靠边界／评分对应的题保持待整理，不伪造坐标。

旧版资料：[v0.4 覆盖与安装](docs/history-v04/README.md) · [旧格式迁移](docs/migration-guide.md) · [导入工作流](docs/import-system-v03.md)。

## 许可

原创程序源码使用 MIT；PyMuPDF/MuPDF 使用 AGPL-3.0 或另行商业许可，二进制附件同时提供对应源代码。Cambridge 题目、图形、考纲和评分内容是独立版权数据，不受程序开源许可授权。本次获确认授权的原卷只随 Release 附件分发，Git 只保存坐标和编者元数据。[许可说明](docs/distribution-licensing.md)。

历史提交曾包含试卷裁片，已按维护者授权清理 main 与版本标签引用的历史，完整备份保存在本机。外部 fork、旧 URL 或 GitHub 缓存不属于普通推送可立即物理清除的范围。
