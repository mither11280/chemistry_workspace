# 题间 · Chemistry Workspace

面向 A-Level 化学教师的本地组卷软件。保留题库浏览、SQLite 筛选、离线描述助手、作业编辑、学生卷/Mark Scheme 导出、个人作业与 `CIE1.` 分享代码。

**当前采用原始 PDF + 公开坐标 JSON + SQLite + 按需 WebP。公开仓库不随附真题文件或原题全文。** 随附 CIE AS Chemistry 9701 的 2024–2026 February/March Paper 12、22 共 132 题坐标。Paper 2 保留整道大题；题目和建议分类经过程序检查，未标记为人工内容复核通过，不能视为完整历年题库。

## macOS 安装包

Apple Silicon 用户可使用独立 DMG：将 App 拖入 Applications，双击运行。不需要 Python、pip、Swift 或 Xcode。包内已包含当前 132 题所需 QP/MS 和内置运行时；首次启动复制到 `~/Library/Application Support/ChemistryWorkspace`。个人原卷、数据库、作业、缓存和导出保存在那里，替换 App 不清空数据。

当前本机输出为 **INTERNAL-UNNOTARIZED 内部测试包**：ad-hoc 签名，没有 Developer ID 和 Apple 公证，Gatekeeper 可能阻止首次打开。不能把它当作正式可信发行版。[完整安装、构建、公证及 Release 说明](docs/macos-distribution.md)。

旧项目通过菜单「题间 → 从旧项目导入数据…」复制。原目录保留，同 ID 不同作业保存副本，当前草稿不覆盖。教师日常界面提供题库更新与报错；旧校准仅作为维护者兼容工具保留。

源码开发版仍可直接运行：

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/server.py
```

开发版默认继续使用项目目录数据；独立包改用 Application Support。构建机需要 Python 3.12 + Xcode，用户无需安装。[许可审查](docs/distribution-licensing.md)明确原创 MIT 源码、AGPL PyMuPDF/MuPDF 和 Cambridge 数据各自的边界；开源许可不授予考试材料再分发权。

## v0.3 自动导入与独立题库更新

维护者可用仓库内 `$question-bank-import` Skill 或 `python scripts/import_bank.py analyze ...` 批量导入新的文本型 CIE 9701 Paper 1/2。引擎统一处理封面身份、QP/MS 配对、跨页坐标、分数与多知识点建议；异常题隔离并可按题修正、缓存重试。自动 QA 不等同人工内容复核，教师无需进入逐题审核工作台。

教师在原题/答案预览点击「题目报错」，检查报告后复制、保存或自行提交预填 GitHub Issue。通过「题库版本与更新」导入 `.qbank`，确认版本/修复说明后安装；保留旧 ID、分享与个人作业。基础 App 仍带 132 题，新增批次包再加入 134 题，安装后共 266 题；随后纯索引修复包独立更新，无需重装 App。

[完整工作流、实测与限制](docs/import-system-v03.md) · [Skill](.agents/skills/question-bank-import/SKILL.md) · [机器验收报告](docs/import-acceptance-v03.json)。程序 Git 仓库保持轻量；取得授权的 PDF 只随 Release 包/题库包分发，不进入 Git 历史。

## 新架构与目录

- `indexes/`：132 题可移植坐标及 Source Manifest，无原题全文、图片或评分原文。
- `schemas/`、`examples/`、`docs/`：独立可解析规范、JSON Schema、原创可重建示例、迁移与性能说明。
- `app/bank/format.py`：格式、来源身份、跨页区域和页面几何校验。
- `app/bank/catalog.py`：SQLite 题库、标签、FTS5/LIKE、事务重建与数据库版本。
- `app/bank/sources.py`：不可变原卷导入、SHA-256/几何验证、本机文本提取。
- `app/bank/render.py`：按需 WebP、缓存限额、从原卷矢量组卷和题序映射。
- `app/bank/migration.py`、`calibration.py`：自动备份、保守迁移、旧 PDF 兼容、可视化框选后保存规范坐标。
- `app/server.py`、`app/app.js`：本地 API 与现有界面；筛选在 SQL 中完成，浏览器按页加载。
- `sources/`、`data/`、`exports/`：仅本机保存原卷、个人状态、缓存、备份和导出，不提交。

每份 QP/MS 只保存一份原始 PDF，题目不预先导出成独立 PDF。坐标单位是 PDF point，page_index 从 0 开始，原点为未旋转 CropBox 左上角。格式定义、原生 PDF 坐标转换及版本规则见 [公开坐标规范](docs/question-index-format.md)。

## 作业、分享与兼容

现有稳定题 ID 和 CIE1 来源哈希规则保持不变。个人作业与草稿仍在 `data/personal.sqlite3`，按题序保存标题、备注与题目列表；可复制、恢复、导入后修改。公开索引重建不覆盖个人作业。

旧题库不会自动删除。已具备可信原卷坐标的题目可迁移；没有可信坐标时保留旧 PDF 浏览/组卷，并标记待校准。维护者设置 `QUESTION_BANK_MAINTAINER=1` 后的「校准区域」支持在原卷上拖动框选、跨页追加、编辑区域顺序，保存前自动备份并验证。详见 [迁移与回滚](docs/migration-guide.md)。

```sh
python scripts/bank_tool.py migrate --legacy "/path/to/old-bank"
# 停止 App 后回滚：
python scripts/bank_tool.py rollback --backup "/path/to/data/backups/migration-TIMESTAMP"
python scripts/bank_tool.py rebuild
```

若原卷被修改，预览、缓存和导出均拒绝使用错误坐标。缓存可删，默认限额 128 MiB。作业 PDF 从原始 PDF 生成，保留矢量文字/化学图形；答案顺序与题序一致，并附 `.mapping.json`。原题号仍可见，Assignment 号为作业题序。clip 不等于 PDF 内容脱敏，可能保留可见区域之外的资源。

## 验证与开发

```sh
python scripts/bank_tool.py validate
python scripts/bank_tool.py validate --index examples/question-index.example.json --manifest examples/source-manifest.example.json
python -m unittest discover -s tests -v
node --check app/app.js
```

测试使用原创生成的 PDF，不需要也不提交 Cambridge 文件。覆盖坐标规范、页面旋转/CropBox、多页、来源哈希、答案顺序、矢量输出、缓存失效、缺卷导入、旧题迁移与失败回滚、CIE1 兼容及个人数据持久化。结构检测与抽查不能代替独立逐题内容复核。

维护命令见 `python scripts/bank_tool.py --help`。已有导入器 `scripts/import_bank.py` 是当前 CIE 批次专用的坐标候选生成工具；其本机中间数据不公开。旧 `package_bank.py` 入口现在迁移坐标，不再制造每题 PDF。

实测与方法见 [性能报告](docs/performance.md) 和 [原始结果](docs/benchmark-results.json)。仅在本地保留旧资料时可执行 `python scripts/benchmark_bank.py` 复测；这不是跨平台基准承诺。

## 发布和内容版权

程序源码使用 MIT 许可。考试题目、图形、考纲及评分内容属于原权利人；源码许可不授予这些材料的使用或再分发权。公开索引不包含原题文本、题图或答案原文。本机导入、备份和缓存默认全部忽略。

**历史说明：** 旧提交曾包含试卷和裁片，现已按维护者授权重写 main 及 v 标签所引用的历史，移除旧题库内容；完整原始 Git 备份仅保存在本机。旧版 v 是历史源码，不是当前安装版本，请使用 main。分支/标签清理不代表 GitHub 的悬空对象、旧 URL、缓存或外部 fork 会立即消失；这些不属于普通 Git 推送可以物理清除的范围。
