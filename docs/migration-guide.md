# 旧题库迁移与回滚

## 迁移原则

不从 question.pdf 反推出原始坐标。只有旧 metadata 的来源身份、原始坐标、源文件 SHA-256 和页面几何均能确认时，才进入坐标索引。旧格式已知只在未旋转且 CropBox=MediaBox 的页面定位；其他旧页面布局一律留待手动校准。迁移保留既有题 ID，不把稳定 ID 换成自增主键。

操作前退出旧版 App，避免旧进程继续修改个人作业。软件内「原卷导入与维护 → 迁移旧题库」或命令行：

```sh
python scripts/bank_tool.py migrate --legacy "/path/to/old-bank"
```

优先读取 index.json（也接受旧导入器的 bank.json），否则扫描 metadata.json。仅有独立裁片而没有可信来源/坐标时，标记 pending_calibration，记录本机旧 PDF，继续浏览和组卷。缺卷但有旧片时界面明确显示「旧 PDF 待校准」；原卷哈希错误时禁止静默回退。只有经校准或可靠迁移的题才写到标准 JSON。

每次迁移在写入前备份 metadata、题目文件和本地 SQLite。SQLite 使用 backup API，捕获已提交 WAL 内容，备份位于 data/backups/migration-*。个人作业不参与公共索引重建；旧题库从不自动删除。重复迁移按稳定 ID upsert，不产生第二份题目。失败会恢复 overlay 和数据库；已导入的相同原始文件可能保留，不会覆盖其他文件。

本次现有 132 道题已按原卷哈希迁移成功，0 道待校准；这只是坐标来源可确认，内容仍 pending_review。

## 手动校准

先导入匹配 Source Manifest 的 QP/MS。在题目卡片点击「校准区域」：

1. 分别选择题目或答案及对应原卷。
2. page_index 从 0 开始。页面显示未旋转的 CropBox；拖动框选，前端换算为 PDF point。
3. 可按页面追加多个区域，或在 JSON 框编辑、删减与调整数组顺序。
4. 点击「备份并保存坐标」，后端验证源哈希、来源身份、bbox 与跨页范围，保存到本机 JSON overlay 后重建 SQL 索引。

校准不会自动标成复核通过。原始 PDF 不修改；发生误操作可用对应备份回滚。新 source_id 尚未登记时应先由维护者建立合法 manifest，当前不提供自动发现题目边界或任意新考试的自动分类。

## 回滚

停止当前 App/服务后运行：

```sh
python scripts/bank_tool.py rollback --backup "/path/to/data/backups/migration-TIMESTAMP"
python scripts/bank_tool.py rebuild
```

恢复个人数据库、catalog 快照和本机 overlay；原卷与旧 PDF 在迁移时从未移除。完整回到旧版软件可切回旧提交，再恢复最初 `data/backups/pre-coordinate-*` 中的个人数据库和旧题库；不要在两个程序版本中同时打开同一个个人数据库。未来结构版本较新时旧程序应拒绝打开。

## 显式归档旧文件

验证题目、来源和个人作业后，用户可以手动归档：

```sh
python scripts/bank_tool.py archive --legacy "$PWD/question_bank/CIE/9701/AS" --confirm
```

命令先验证所有必需原卷可用、旧 index 中每题都已进入新索引，再把旧目录移动到 data/legacy-archives/。不自动删除。若不迁移/归档旧目录，它会继续占用磁盘；性能报告的新架构大小不包含备份和刻意保留的旧文件。归档不是节省这部分磁盘的永久删除动作，删除由用户自行决定。

## GitHub 边界

当前公开工作树仅保留代码、坐标 JSON、Schema、测试、原创示例和文档。sources、旧题库、原卷、独立裁片、个人数据和缓存全部忽略。此前提交曾包含 PDF。维护者本次已明确授权：先保留完整本地 Git bundle，再在隔离副本中重写 main 和 v 标签的可达历史，移除全部旧 question_bank/CIE 文件（包括 PDF、提取正文的 metadata 和索引）。源码提交关系和考试文件以外的修改保留。旧 Git 备份仅在本机 data/backups 中，不推送。

分支/标签引用清理不等于 GitHub 物理擦除悬空对象、缓存、旧 SHA URL 或外部 fork。若旧直链仍可访问，需通过 GitHub 的仓库支持/缓存清理流程处理；不能声称普通 force-with-lease 推送已删除所有平台副本。历史旧版 v 作为源码参考，用户应从 main 下载新版。
