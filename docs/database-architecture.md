# 本地数据库与数据流

## 三层结构

```text
indexes/                      可公开交换的 JSON 原始数据
schemas/                      JSON Schema + 公开规范
sources/cie/9701/...           本机原始 PDF（不提交）
data/catalog.sqlite3          可重建题目/来源/搜索/旧题兼容数据库（不提交）
data/personal.sqlite3         既有个人作业和草稿（不提交）
data/question-index.local.json 本机迁移、手动校准的 JSON overlay（不提交）
data/source-manifest.local.json 本机来源 overlay（不提交）
data/cache/webp/              可选、可删的按需预览缓存（不提交）
data/backups/                 迁移前备份（不提交）
exports/                      作业 PDF 与题号映射（不提交）
```

JSON 是标准数据源，SQLite 是派生查询层；本机手动校准也写回可验证 JSON，不只保存在数据库。公开 JSON 与 local overlay 按稳定 ID 合并，本机校准优先。删除 local overlay 会撤销本机校准；撤销前应先备份。

## catalog.sqlite3 v2

- sources：source_id 主键、标准 source JSON。
- questions：稳定 question_id 主键；year、paper、marks、type 列及组合索引；规范 JSON payload。
- tags：题目与多个知识点的关联，topic 索引。
- search：支持时用 FTS5/unicode61；不可用时退回参数化 LIKE。搜索原题文本只来自本机校验过的 PDF。缺卷时仍可搜索 ID、知识点和英文分类标签。
- local_content：仅本机提取的题干文本、MCQ 答案、QP 哈希及 MS 哈希。哈希改变后旧文本不参与 FTS，旧答案不用于输出。
- legacy：尚待校准的旧 metadata 与本机 PDF 路径，不进入公共索引。
- settings：数据 fingerprint 和 FTS 能力记录。

PRAGMA user_version 管理数据库结构。v0→v1 建表，v1→v2 增加 MS 内容身份校验列；更高版本拒绝被旧程序降级打开。索引重建单事务更新公共来源、题目、标签和 FTS，保留个人数据库及 legacy；local_content 只对匹配的当前源哈希生效。

personal.sqlite3 保留原 jobs(id,title,body,updated) 和 draft(slot,body)，题目顺序、教师备注仍在已有 JSON body。v1 仅登记数据库版本并补齐表，不重建用户数据。两库逻辑与物理分离：重建公共题库不能清空作业。用户删除正在使用的题目索引时，草稿不会自动覆盖；界面会提示缺失 ID 并保留原数据库。

## 读取与写入

1. 启动时校验公共 JSON 与本机 overlay，fingerprint 不变时复用 SQLite；不扫描每题文件夹。
2. 列表按 SQL 条件与 LIMIT/OFFSET 查询；浏览器只收到当前页。作业单独按稳定 ID 加载。
3. 预览：查询题目 → 校验来源哈希/几何 → 未旋转 CropBox 上按 bbox 渲染 → 可选 WebP。
4. 用户批量上传或 CLI 导入：按 SHA-256 识别，文件名只作提示；同名异版拒绝、不同名同内容可识别。暂只接收 manifest 已登记的源；扩充新试卷需先提供来源 manifest 和已校准坐标。写入临时文件再原子改名，已有异内容目标从不覆盖。
5. 导出：同一原卷在一次组卷内只打开一次，按 regions 用 show_pdf_page/clip 生成矢量 Form；题序与答案顺序均以作业 ID 列表为准。输出附 `.mapping.json`。

缓存键包括题 ID、源哈希、完整 regions、块序号、比例、后端类型和渲染版本；即使命中缓存，也先验证来源。默认上限 128 MiB，按访问时间清理最旧 WebP；关闭缓存仍能预览，导出不读取 WebP。`/preview/...?cache=0` 跳过缓存。UI 和 CLI 均可清空缓存。

HTTP 只监听 127.0.0.1，写入要求 X-Local-Request 和匹配的 Origin/Host。源上传上限每文件 64 MiB，逐文件返回结果，不从第三方站点下载。

## 矢量与隐含资源

show_pdf_page 的可见 clip 不保证源页面资源从文件中物理删除。输出可能携带可见区域之外的文字/图形资源，不能视为内容脱敏。此实现保留矢量质量，复用源文档、garbage=4、deflate=True；实际文件大小见性能报告。要在不引入破坏性重写的前提下进一步剔除隐藏资源，需要另行验证，当前不宣称实现。
