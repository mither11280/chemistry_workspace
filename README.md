# 题间 · CIE AS Chemistry 本地题库

这是可在当前 Mac 使用的 v0.1 开发版。界面使用原生 macOS 窗口，题库、草稿、个人作业与 PDF 都留在项目目录；不需要账号、云端服务或 API Key。

## 启动

双击 `题间.app`，或者双击 `启动.command`。**请保留整个项目目录，不要只把 .app 单独移走。** 当前使用这台 Mac 已安装的 Python 3.9 + PyMuPDF，路径记录在 `runtime.json`。这不是已签名、捆绑运行时的通用安装包；另一台 Mac 需要 Python 3 + PyMuPDF 后执行 `scripts/build_app.sh`，Windows 桌面壳尚未制作。

开发时可运行 `python3 app/server.py`，然后打开终端显示的本机 URL。服务只监听 127.0.0.1，拒绝不匹配的 Host 和跨站写请求。退出原生 App 会终止它启动的服务。

## 已实现

- **题库**：Paper 1 / Paper 2、年份、建议知识点、题干与来源编号搜索；原题图、官方评分标准、完整原卷查看。
- **组卷**：加入与移除、上下移动排序、标题与说明、题量与分值统计；Paper 2 可展开全部跨页内容。
- **离线描述助手**：规则识别知识点、题量、Paper、年份，再由教师确认条件；随机选题，避开当前作业已有题。不足时明确提示，不自行放宽条件。不是大模型，不理解复杂排除、难度或教学进度。
- **个人作业**：SQLite 草稿自动保存、命名保存、重新打开、复制和删除。导入分享后是独立草稿。
- **分享**：`CIE1.` 压缩代码与 `.ciepaper` 文本文件；包含来源 SHA-256、稳定题目 ID、顺序、标题和说明；缺题、来源版本不同或损坏代码会被拒绝。没有短链接或云社区。
- **PDF**：学生卷及官方评分标准卷，保留原始矢量图形和跨页内容，双编号（作业题序 + 原题号），包含参考数据/评分原则。生成文件写入 `exports/`，原生窗口通过系统 PDF 应用打开，可另存或打印。

## 题库覆盖与内容状态

| 考季 | Paper 1 (12) | Paper 2 (22) |
|---|---|---|
| 2024 March | 40 题 / 40 分 | 4 道大题 / 60 分 |
| 2025 March | 40 题 / 40 分 | 4 道大题 / 60 分 |
| 2026 March | 40 题 / 40 分 | 4 道大题 / 60 分 |

共 132 道题。来源是用户提供的本地 QP / MS，已复制至 `data/sources`，附 2025–2027 考纲。原始文件未改动。每道题保留原始页序、裁剪坐标、题号、分值、来源哈希与状态。

**这是待复核的起始题库，不是完整历年题库或正式验收题册。** 自动分割、答案区域匹配及关键词分类未经独立逐题内容验收，所有题目维持 `pending_review`。标签是候选主题，尚未建立逐条考纲映射；旧年份不宣称完全符合现行考纲。PDF 显式标注教师试用稿。

Paper 2 目前以完整大题为最小组卷单位，不支持独立小问选择；通过保留整题来避免丢失共享条件。后续应依据切题技能建立小问依赖、评分点配对和独立复核记录后再开放小问组卷。

## 文件和备份

- `app/`：本地 HTTP API、PDF 引擎、HTML/CSS/JS 界面。
- `native/`：Swift + WKWebView 桌面窗口，负责服务生命周期与本机文件打开。
- `data/bank.json`：可重建题库清单、裁剪区域、来源与覆盖统计。
- `data/sources/`：本地原卷、评分标准和考纲副本。
- `data/personal.sqlite3`：个人作业与当前草稿。备份时退出 App 后复制这个文件；建议连同整个 `data/` 备份。
- `data/cache/`：题图缓存，可重建。
- `exports/`：用户导出的 PDF；`tests/` 中的 PDF 为验收示例。
- `scripts/import_bank.py`：起始批次导入器。重新运行会重建题库索引，不会清除个人作业；若修改裁剪区域，应同时清理对应图片缓存。此脚本只针对当前批次验证过的版式，不能不经检查直接扩到所有年份。

## 开发与测试

依赖：Python 3 + `PyMuPDF`；原生构建另需 Xcode Command Line Tools / Swift。前端没有构建步骤、CDN 或运行时外网依赖。

```sh
python3 -m unittest discover -s tests -v
node --check app/app.js
./scripts/build_app.sh
```

自动测试覆盖题量与分值、来源哈希、区域边界、分享往返及版本冲突、恶意过大代码、未知/重复题目、数据库持久化、PDF 的题序与草稿标记。内容正确性不能由这些结构测试代替。界面已在当前 Mac 原生窗口验证选题、命名保存与个人作业流程。

下一阶段：逐题内容复核与准确考纲分类 → Paper 2 小问和依赖 → 扩充年份 → 独立运行时打包与 Windows 版本。


## 从 GitHub 恢复

仓库保存源码与文档；真题 PDF、提取题干和本机路径的 `data/bank.json`、个人作业数据库、图片缓存、测试导出、`runtime.json` 与编译出的 `.app` 都不提交。已在本机的这些文件不受上传影响。

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/import_bank.py --source-root "/path/to/9701" --syllabus "/path/to/9701-syllabus-2025-2027.pdf"
./scripts/build_app.sh
```

`--source-root` 下应有 `2024_M`、`2025_M`、`2026_M`，每个目录包含 `9701_mYY_qp_12.pdf`、`9701_mYY_ms_12.pdf`、`9701_mYY_qp_22.pdf`、`9701_mYY_ms_22.pdf`（YY 为 24、25、26）。题库索引和预览缓存目录会自动生成。

Mac 构建需要 Swift / Xcode Command Line Tools。也可直接运行 `python3 app/server.py`，在浏览器中打开打印的本机地址。完整功能测试需先导入题库；没有题库时可运行 `python3 -m py_compile app/server.py scripts/import_bank.py` 和 `node --check app/app.js` 检查源码。
