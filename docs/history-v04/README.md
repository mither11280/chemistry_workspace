# v0.4：2018–2026 历年题库

本次保留 v0.3 的本地 App、坐标 JSON、SQLite、WebP 和矢量 PDF 架构，实际扩充到 **2,523 题**，在已有 266 题之外新增 **2,257 题**。旧题 ID、来源哈希、题目内容/答案区域、分数和标签保持不变；原考试年份、考纲周期和当前兼容性分开记录。

## 覆盖范围与未入库资料

完整 [逐年份/考季/Variant 矩阵](coverage.md)、[CSV 与源文件 SHA-256](coverage.csv)、[机器报告](coverage.json)、[19 题隔离原因及 QP/MS 分数](anomalies.json)。

- 2022–2025 未入库考季及 variants：新增 1,007 题，11 题隔离。
- 2026 已取得的成对 QP/MS：新增 16 题，0 题隔离。
- 2018–2021 旧版：新增 1,234 题，8 题隔离。
- 现有 266 题对应的 12 对试卷没有重复导入；题目 ID 和完整考试身份重复数均为 0。
- 普通缺卷共 5 份 QP：2023 May/June 21、2023 Oct/Nov 21、2026 May/June 11/12/13。目录中存在对应 MS，但不据此伪造题干。
- 2026 Oct/Nov 六个 components 在统计日尚未完成，单列为等待考季完成，不算普通缺卷。
- 两个不合格副本被排除：2023 的课堂改写副本无法可靠识别封面；2025 的另一份 QP21 副本仅 13 页、封面声称 16 页。
- 一组 2025 QP23 异哈希副本的逐页未旋转 boxes、文字位置与 RGB 像素完全相同，仅附录显示旋转/保存信息不同。保留选择记录，只收一份，不改写原卷。

2020 May/June 的取消状态来自 [Cambridge 官方公告](https://www.cambridgeinternational.org/news/news-details/view/update-from-cambridge-international-on-may-june-2020-exams-20200323/)；相应本地资料仅按已公开练习材料收录。没有抓取第三方 PDF。

## 已增强的导入系统

`$question-bank-import` 现在先生成 inventory，再按 modern → year2026 → legacy 三阶段运行。统一模块负责封面/文件名核对、QP/MS 配对、缓存、跨页坐标、答案和分数、一致性门禁；未通过项不进入公开题库。单卷可使用原 analyze 命令重试，阶段可使用 `--phase` 及其上一阶段 `--base` 重试。

旧版使用独立策略，Section B 每题前置原卷共用答题编码表。MS 在阅读布局中识别后逆变换回规范坐标，原始 PDF 和 native CropBox 均不修改。2026 的 Guidance 说明栏数字不会计入 Marks。对已观察到的错误 ToUnicode，仅在封面化学科目与试卷代码两组编码证据一致时使用只读解码，无法证实的编码仍隔离。

增加阅读方向的可选 source metadata 和相应缓存键；公开坐标仍为 schema 1.0.0、PDF point、0-based、未旋转 CropBox 左上角。详情见 [坐标规范](../question-index-format.md)。

扩容发现并修复了批量文字索引中的 SQLite 锁冲突：在写事务之前读取来源快照，事务中不通过第二连接重复查来源。安装校验复用有限数量的已验证 PDF 文档，减少逐题重新打开同一文件的开销。

## 获取与安装

使用 v0.4 App。历史坐标、显示方向、编码和 Guidance 校验需要新版后端，更新包声明最低 App 版本 0.4.0；旧 v0.3 App 应先更新。

- 首次安装/仍为原 132 题：导入 `ChemistryWorkspace-v04-full-from-132.qbank`，一次到达全部 2,523 题。
- 已安装 v0.3 的 266 题整合包：导入 `ChemistryWorkspace-v04-full-from-266.qbank`。
- 维护者增量发布：三个分批包严格依赖 v0.3.2 → v04.1 → v04.2 → v04.3。

所有路径最终收敛到同一 `2026-10-27.v04.3`，避免新教师逐个安装历史包。App 先展示版本及修复说明，用户确认后备份、验证及原子激活。个人作业不在更新包内，原文件缺失仍显式提示。

回滚时退出 App：

```sh
python scripts/import_bank.py rollback <安装返回的backup_id> --home /path/to/profile
```

旧 generation、原卷和备份保留，不恢复或覆盖个人作业库。回滚到尚无新题的版本时，新题作业记录仍保存，恢复对应题库后可继续使用。

## 可复现维护流程

```sh
python scripts/import_bank.py inventory /path/to/9701 --base /path/to/266-snapshot --output data/history/inventory
python scripts/expand_9701_bank.py --corpus /path/to/9701 --base /path/to/266-snapshot --output data/history --revision-prefix 2026-10-27.v04
python scripts/verify_historical_bank.py --corpus /path/to/9701 --workdir data/history --base /path/to/266-snapshot --authorization /path/to/rights.json
python scripts/publish_bank_reports.py --workdir data/history
```

统计日默认取运行当天；复现本次冻结矩阵可传 `--as-of 2026-10-27`。使用全新验收 profile 目录；脚本拒绝覆盖现有验收 profile。需要重跑时先把此前验收目录归档。正式用户数据目录不参与这些测试。

`indexes/releases/v0.4-2018-2026/` 保存可独立解析的完整坐标快照，无题干全文/评分原文。`coverage.json`/CSV、异常、批次报告、授权和验收结果均可公开。解析缓存、原卷、WebP 和个人数据库留在被忽略的本地目录。

## 授权、验证与限制

维护者在本次任务中明确确认：授权覆盖本地提供的 2018–2026 全部 Paper 1/2 QP/MS，含 2020 取消考季已公开练习资料。逐文件年份、角色和 SHA-256 记录在 [authorization.json](authorization.json)。这是维护者直接确认的记录，不是伪造的权利人证书；原版权不随软件 MIT/AGPL 许可转授。

本次 56 项自动化测试通过，包含实际 2018–2021 四个历史年份、2023 编码异常卷和 2026 Guidance 布局回归；公共 CI 不含私人原卷，会明确跳过需要本地 corpus 的两项真实样本测试。完整数据的 [实际验收测量](acceptance.json) 验证分批与累计安装、70 个预览区域、20 题混合年份/乱序学生卷和答案卷、回滚重装，以及个人数据库逐字节保留。

自动 QA 不是人工内容复核或统计准确率。19 题仍因答案缺失/分数不匹配隔离。旧题的逐条当前考纲兼容性为 unknown；宽泛知识点到当前章节只是候选映射，原文档修订号不明时保留 null。旧卷若依赖另行发放的 Data Booklet，教师需提供对应版本，本次未下载或静默换用新版本。扫描件、其他科目/卷型、OCR 和自动联网更新不在本版范围。

冻结运行时验收也已通过：[实际 DMG 安装/重启/升级](native-install-verification.json) 与 [冻结后端完整题库更新](frozen-bank-verification.json)。后者以空 PATH/PYTHONPATH、无开发工作目录、隔离 profile 通过 HTTP 从 132 题更新到 2,523 题，验证旧分享、保存作业、历史共用规则/旋转 MS 预览、学生卷/MS 导出和报错预填；安装及文字索引合计约 44 秒。

本机模块级累计包校验安装约 39 秒；20 题混合年份作业学生卷约 1.11 秒、4.16 MB，答案约 0.78 秒、1.75 MB。70 个预览区域约 2.8 秒。它们是本机这份样本的单次结果，不是普遍性能保证。
