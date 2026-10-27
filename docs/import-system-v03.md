# v0.3 维护者导入、教师报错与题库更新

## 现有模块的延续

沿用 vanilla JS 本地网页、Swift/WebKit macOS 外壳、Python HTTP 后端、PyMuPDF 矢量导出、SQLite/FTS5 与 WebP。公开 JSON 坐标规范仍为 1.0.0；没有重写 UI 或更换 PDF 技术栈。个人作业仍在独立 `data/personal.sqlite3`，本次更新器不打开该库。

教师使用现有题库/组卷/个人作业界面，并在题目或答案预览中使用「题目报错」。题库维护入口改为「题库版本与更新」，校准/批量切题不再作为教师日常任务。维护者仍可设置 `QUESTION_BANK_MAINTAINER=1` 使用旧手动校准兼容工具；没有强制逐题人工复核工作台。

## 目录和契约

- `.agents/skills/question-bank-import/`：可直接调用的 `$question-bank-import`，命令细节在 references。
- `app/bank/importer/identity.py`：读取封面年份、考季、卷型、variant、角色与总分；标准文件名交叉核对，非标准文件名可按封面识别。
- `parsing.py`：主问题锚点、跨页区域、QP 分值、MS 行与分值、附录区域。
- `quality.py`：题号连续性、QP/MS 题号与总分、一题分值、空白/边界/横向文字切边、答案裁图身份与实际分值。选择题要求对应题号及唯一答案字母。
- `topics.py`：多标签关键词规则及启发式支持分数，不是统计概率或考纲逐条认证。
- `engine.py`、`types.py`：独立可测试的批次协调、类型约束、带版本缓存、按题修正、异常隔离和完整快照输出。
- `scripts/import_bank.py`：薄 CLI，analyze/package/install/rollback；不再限于原 2024–2026 March 固定批次。
- `app/bank/updates.py`：校验更新包、不可变 generation、备份、原子激活和回滚。
- `app/bank/feedback.py`：报告白名单、路径脱敏、离线 Markdown、GitHub Issue 预填链接；不发送 Issue。

`analyze` 的 workdir 只能放在被忽略的本地目录。解析缓存含合法取得的 PDF 文字，`source-files.private.json` 含本机路径；这些不是公开坐标规范的一部分。公开题目只包含元数据、坐标及可选结构化选择题答案，不包含题干全文、图片、评分原文。

## 自动导入和异常处理

```sh
python scripts/import_bank.py analyze /path/to/selected/pdfs \
  --workdir data/import-work/batch1 --revision 2026-10-27.batch1
```

目录可以递归扫描，但建议选择明确批次。相同身份和相同哈希副本去重；同身份不同哈希隔离，不猜版本。缺配对报告为批次异常。源文件打不开、封面无法识别、文件名与封面冲突、扫描件等留失败记录。

候选逐题经过 Schema、来源身份、几何、跨页、答案和分值检查。全卷题号/总分异常暂缓整卷；题目局部异常隔离该题，其余通过项可发布。原先已有而本次失败的题不会被删除或覆盖。报告明确 detected/accepted/quarantined、缺题号、缺答案、文件级失败及 cache_hit。

缓存键包含两份原卷哈希与 parser version；解析器变动必须提升版本。重复运行复用解析结果，仍重新执行 QA。修正文件携带 source_fingerprint，支持单题 question/answer/marks/topics；每次重新校验。全卷锚点缺失不能靠单题 override 绕过，需修正解析器或明确保留异常。Skill 的 [工作流](../.agents/skills/question-bank-import/references/workflow.md) 提供完整命令。

## 题库更新包

`.qbank` 是 ZIP，版本 1.0.0：

```text
update.json
question-index.json
source-manifest.json
sources/...pdf             # 可选，必须逐文件取得再分发授权
```

update.json 保存 bank_id、base_revision、revision、minimum_app_version（当前为 0.3.0）、changelog、所有成员的 SHA-256 及授权声明。索引是完整快照。基于版本必须精确匹配，不自动猜测合并冲突；旧 question_id 的考试身份不可修改、不可删除，旧 source_id/路径/哈希必须保留。更换 PDF 版本必须新增 source_id。

App 的「题库版本与更新」选择包 → 校验并展示说明/哈希 → 用户确认安装。更新器校验归档成员、重复名、路径跳转、大小上限、哈希、Schema 和可用原卷区域；含隔离状态的改动不准安装。没有源 PDF 的纯索引包允许安装，但题目显示缺失资料，不能假装预览成功。

数据写入 `data/bank-updates/generations/<uuid>/`，一次原子切换 `current.json`。切换前备份可重建 catalog 及旧指针，索引事务失败恢复旧指针与 catalog。异常中断后下次启动按指针和指纹重建。原卷只新增、不会覆盖不同哈希文件；失败时新原卷可能留存供重试，不删除任何用户文件。

读取优先级：随 App 的基础快照 → 当前管理更新快照 → 用户明确手动校准/自有题覆盖。旧迁移产生的全库 local 快照不会遮住公开修复；显式 `metadata.calibration=manual` 仍优先，维护者更新不会静默抹掉个人校准。个人自有题保留。个人作业、草稿、教师备注完全独立。

回滚：退出 App 后执行：

```sh
python scripts/import_bank.py rollback <backup_id> --home '/path/to/profile'
```

不恢复个人作业库；旧 generation 和备份不会自动清理。更新包 SHA-256 用于完整性，不是发布者签名；只从可信维护者发布地址取得包。本版不实现自动联网检查更新、签名更新或增量二进制补丁。

## 教师报错和隐私

预览 →「题目报错」→ 选裁切/答案/知识点/分数/其他 → 填说明 → 生成并检查报告。

白名单只含题目 ID、考试身份、源 ID/文件名/SHA-256、题库 ID/revision、App 版本、用户说明。服务端忽略其他输入，不读取个人作业、认证信息或本机路径；说明里的常见本机路径会脱敏，用户仍应检查并避免填学生隐私。报告可以复制、保存为 `.md`，或打开固定仓库的 GitHub Issues 预填页，用户登录后自行点击提交。没有 GitHub Token、自动上传、遥测或后台发信。原生外部打开只允许该仓库 Issues/new 路径。

## 实测验收与限制

可复现脚本：

```sh
python scripts/verify_import_acceptance.py --corpus /path/to/9701 \
  --workdir data/acceptance-fresh --report docs/import-acceptance-v03.json
```

该脚本只在指定隔离目录生成题库、测试作业与更新包，首次使用应给新 workdir；不会修改真实用户 profile。固定选择 2023 March 12/22、2024 October/November 13/23（非标准文件名）和 2025 May/June 11/21 六组 QP/MS，另重跑原有 132 题。

本机一次实测：新增 134/134 题通过当前自动门禁，隔离 0、题号缺口 0、缺答案 0，六组 QP/MS 题数及分值一致；原 132/132 重新解析通过，公共原数据不改。二次运行六组缓存均命中。初始批次用时约 5 秒；精确原始测量见 [JSON 报告](import-acceptance-v03.json)。

20 题（含一道跨页 Paper 2）按倒序混排测试：学生卷约 0.20 秒、859,170 字节，答案约 0.12 秒、264,886 字节；首次预览约 0.054 秒、缓存约 0.001 秒。数字是本机这份作业的单次结果，不是性能保证。

完整链路还验证了歧化反应题 `cie-9701-m23-12-q1`：启发式未分类 → 生成知识点报告 → 根据原文修正为 electro → 重新 QA → 安装约 20 KB 纯索引修复包 → 回滚 → 重装；保存作业 DB 逐字节不变，旧题仍可预览。134题含资料新增包约 4.46 MB。没有实际向 GitHub 提交测试 Issue。

范围限制：目前仅文本型 CIE 9701 Paper 1/2；无 OCR、无 AI 辅助或其他学科解析器。关键词标签不保证 syllabus 映射正确。文字/几何及分值一致性不能证明图表语义完整或所有排版均适用；自动通过不等同人工复核，也不能把本批次比率称为统计识别准确率。底层矢量 PDF clip 仍可能带可见范围外资源，正式导出不栅格化。

## 自动化与安装包验证

本次完整 `unittest discover -s tests -v` 为 43 项通过；包括旧规范/迁移/缓存/PDF/分享回归、新解析缓存和修正隔离、来源授权、更新包路径和哈希、事务失败恢复、自有题保留、反馈隐私及 HTTP 上传预览→确认安装流程。`node --check app/app.js` 与 Skill quick_validate 通过。

Apple Silicon v0.3.0 也构建为包含内置运行时和原 132 题资料的独立 DMG，在临时目录实际挂载、复制和运行，空 PATH/PYTHONPATH、无源码工作目录下完成检索、预览、导出、分享、报错预填、保存与升级保留验证。当前仍为 ad-hoc 签名的 INTERNAL-UNNOTARIZED 测试包，未取得 Developer ID 签名/Apple 公证。
