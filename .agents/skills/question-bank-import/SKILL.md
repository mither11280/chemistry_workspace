---
name: question-bank-import
description: 为题间维护者批量导入 CIE 9701 Paper 1/2 的 QP/MS，运行统一 Python 引擎生成坐标索引、自动质量报告、可重试修正与独立题库更新包。用于新试卷入库、批次异常处理和已报错题目修复。
---

# 题库自动导入

这是维护者工作流。教师在 App 中浏览、组卷、报错，不承担强制逐题审核任务。

在包含 `app/bank/importer/`、`schemas/`、`scripts/import_bank.py` 的仓库根目录操作。使用已经安装 requirements 的 Python 3.11+；以下 `python` 指该解释器。批次、修正、打包和安装的实现统一在 Python 模块，不能另写一套提示词切题逻辑。

1. 确认用户提供的本地 PDF 范围、逐年份再分发授权及基础题库版本。历年扩充先用 `inventory` 扫描已有题库与本地文件，区别取消/未结束考季；再用 `scripts/expand_9701_bank.py` 按新版、2026、旧版分阶段处理。支持 2018–2026 文本型 CIE 9701 Paper 1/2；扫描件、其他科目或卷型先留异常，不猜测坐标。无需联网下载试卷。
2. 调用 `python scripts/import_bank.py analyze <文件或目录> --workdir data/import-work/<批次> --revision <新版本>`。封面识别、文件名交叉核对、QP/MS 配对、跨页裁切、分值和知识点建议均由引擎完成。若安装过更新，先使用当前公开 generation 的两个 JSON 作为 `--base`，不要用包含个人手动覆盖的索引作为公共基础。
3. 阅读 `report.json` 与 `quarantine.json`。自动检查通过只表示程序一致性通过，不是人工内容复核。隔离题目不得发布；部分通过的批次可以仅发布通过项，报告未发布的数量。遇全卷题号/总分异常，保持整卷隔离。
4. 修正时读取 [修正与重试](references/workflow.md)。仅按原 PDF 的可验证证据修正，携带原卷指纹；保持 question_id 和既有 source_id/哈希。重复 analyze 复用解析缓存，修正结果仍需全部质量门禁。旧 Section B 保留共用答题编码表；原考纲周期与当前兼容性分别记录，未知不可标记兼容。不要仅改 QA 状态绕过隔离。
5. 用 `package` 子命令生成 `.qbank`，说明新增/修复内容。需要附原卷时使用明确授权声明和精确 SHA-256 清单；没有对应授权时生成纯索引包。不要把 PDF、缓存、个人作业或私有解析文字提交进 Git。
6. 在隔离 home 先 `install`，实际搜索、预览、按顺序组卷和答案导出。验证旧题 ID 与保存作业仍可读，记录真实计数、异常及测试范围。公开发布与 GitHub 操作遵循用户已经授权的范围。

需要具体命令、恢复方法、目录和限制时再读 [workflow.md](references/workflow.md)。格式详情见仓库 `docs/question-index-format.md`；引擎测试在 `tests/test_import_system.py`。不要为通过验收伪造边界、评分或准确率。
