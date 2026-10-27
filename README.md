# 题间 · Chemistry Workspace

面向 A-Level 化学教师的本地组卷软件。保留题库浏览、SQLite 筛选、离线描述助手、作业编辑、学生卷/Mark Scheme 导出、个人作业与 `CIE1.` 分享代码。

**当前采用原始 PDF + 公开坐标 JSON + SQLite + 按需 WebP。公开仓库不随附真题文件或原题全文。** 随附 CIE AS Chemistry 9701 的 2024–2026 February/March Paper 12、22 共 132 题坐标。Paper 2 保留整道大题；题目与知识点仍为待逐题复核的候选，不能视为完整历年题库。

## 安装与首次使用

Python 3.9+，本地运行，无账号、API Key 或 CDN 依赖。

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/server.py
```

Windows 激活虚拟环境使用 `.venv\Scripts\activate`。打开终端输出的 127.0.0.1 地址：即使还没有原卷，也能浏览题目元数据、筛选、编排和保存作业；预览与正式导出会明确提示缺失文件。

点击页面上方或侧栏的「原卷导入与维护」，批量选择**自行合法获取**的 Question Paper、Mark Scheme（可附考纲）。程序按 manifest 的 SHA-256 识别，文件名只作提示；同名不同版本不会关联，已有不同内容文件不会被覆盖。不从第三方网站自动下载试卷。

当前来源清单为各年份的 `9701_mYY_qp_12.pdf`、`9701_mYY_ms_12.pdf`、`9701_mYY_qp_22.pdf`、`9701_mYY_ms_22.pdf`（YY=24/25/26）及 `9701-syllabus-2025-2027.pdf`。不同字节版本即使题目相似也不能套用现有坐标；需要显式登记该版本及校准。原题全文只在导入后提取到本机搜索数据库。

也可从命令行批量导入：

```sh
python scripts/bank_tool.py import "/path/to/legally-obtained-pdfs"
python scripts/bank_tool.py check
```

macOS 原生窗口需要 Xcode Command Line Tools / Swift：在虚拟环境激活后运行 `./scripts/build_app.sh`，再打开 `题间.app`。保留整个项目目录，当前尚未提供捆绑 Python 的独立安装包。Windows/Linux 可使用本机浏览器入口，未提供原生壳。

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

旧题库不会自动删除。已具备可信原卷坐标的题目可迁移；没有可信坐标时保留旧 PDF 浏览/组卷，并标记待校准。题目卡片中的「校准区域」支持在原卷上拖动框选、跨页追加、编辑区域顺序，保存前自动备份并验证。详见 [迁移与回滚](docs/migration-guide.md)。

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
