# 可靠性重构：两批可复现修复

这是 v0.6 开发过程中的 Goal 1 检查点，不是整个工作台目标已经完成，也不是已发布的新安装包。稳定下载仍是 v0.5.1。Paper 5、剩余待整理题及教师工作流／PDF 排版优化继续进行。

## 当前结果

以提交 `e5afa5baa28a1db63f1100666202cdbab02bb99b` 的 v0.5.1 公开快照为基线。

| 范围 | 原可用／待整理 | 本批可用／待整理 |
| --- | ---: | ---: |
| Paper 1 | 2280／0 | 2280／0 |
| Paper 2 | 2109／68 | 2126／51 |
| Paper 4 | 3277／264 | 3351／190 |
| 合计 | 7666／332 | 7757／241 |

全部 7,998 个稳定 ID 和 352 份来源的 ID、路径、哈希保留。没有修改任何原始 PDF。合计 15 个 AS 小问重新定位了官方 MS 区域；其他变动没有移动题目或答案坐标。

第一批 47 个恢复单位的顺序互斥统计：

1. 字体边界框误报重新验证，以及相应前问解除隔离：15 个。
2. 旧式 MS 标签已能被现有解析器精确识别，重新测量并阅读确认：13 个。
3. 教师确认臭氧化／环加成可归第 11 章后，材料检查同时通过：4 个。
4. 教师确认有机立体异构／普通羰基还原的章节规则后，材料检查同时通过：15 个。

另外有 29 个原来已经可用的有机小问按确认后的教学规则改归第 11 章；不是新增题量。8 个臭氧化／环加成问、46 个有机立体异构／还原问均保留带材料指纹的决定记录；有缺页或裁切异常的继续待整理。

第二批再恢复 44 个，当前快照为 `2026-10-29.reliability.9`：

| 修复 | 直接核对单位 | 新恢复可用 |
| --- | ---: | ---: |
| 基础有机／含苯环杂化计数 | 78 | 26 |
| 官方 MS 父标签代替缺失的首个 roman 标签 | 2 | 2 |
| 氧化还原配平／滴定计量、VSEPR | 14 | 13 |
| 碘仿检验 | 2 | 2 |
| 氮氧化物来源的暂定教学收纳 | 1 | 1 |

已经可用题的重新分类不计作新增题量；直接核对后仍有材料问题的也不计入恢复数。基础有机归 11，含苯环的杂化计数归 7，基础配平／滴定归 3，VSEPR 归 6。氮氧化物来源是教师暂定放入 9 的单题收纳例外，不意味着它考查胺／酰胺。

[总报告](checkpoint.json) · [全部待整理 JSON](pending.json) · [CSV](pending.csv) · [材料接口验收](source-acceptance.json)。`docs/paper4/` 和 `docs/teaching19/` 原来的 v0.5.1／v0.5.0 报告保留为历史基线，不将历史发布数值改写为本次开发数值。

完整自动测试 145 项通过，无跳过，包含设置本地 `CIE_CORPUS` 的真实样本回归；测量见[总报告](checkpoint.json)。全部 7,998 条公开判断的材料指纹重新核对一致，公开索引不嵌入选择题官方答案。实际已发布快照的四类升级检查见[基础／完整包采用测试](bundled-adoption.json)。[第一批总报告](checkpoint-batch1.json)与[第一批接口验收](source-acceptance-batch1.json)保留历史结果。

## 两份集中异常原卷

| 原卷 | PDF 页树／实际页数 | 封面声明 | 本地未找到的印刷页 |
| --- | ---: | ---: | --- |
| 2024 May/June 43 | 25／25 | 28 | 26、27、28 |
| 2026 March 42 | 23／23 | 28 | 2、17、26、27、28 |

两份 PDF 打开时均未触发 MuPDF 的修复模式，页树计数与实际读取一致。不是当前 PDF 读取器简单少算了页；本地文件不含上述声明页。尚未取得足够证据证明它们全部是空白或非必需内容，因此原有 57＋55 个单位继续保留来源完整性门禁。全部识别分值均为 100 不能替代这个检查。

详细印刷页与源 SHA-256 在 [裁切检查报告的 source_audits](edge-repair-report.json)。不能把另一变体的附页当作本变体原页，也不能填造缺失坐标或修改既有源哈希。

## 修复方式和质量边界

`crop_edges.py` 只处理字体框穿越边界的情况：把落在裁切框外的字体框区域变换回规范的未旋转坐标，按 288 dpi 渲染，只有整块没有可见墨迹才排除该误报。像素格向外取整；遇到文字、化学键等墨迹、越界或无法测量时保持警报。它不移动裁切线，不忽略实际缺页，也不证明某个完全未纳入裁图的上下文已经齐全。

MS 修复要求同时满足：旧材料指纹、明确的图文核对记录、重新测得的答案指纹、精确完整小问标签、分数相等、QP／MS 几何与边界检查。旧 `3(b)(iii)` 被错误并入后续紧凑 `3c(i)` 的评分内容等情况，按新边界分别恢复；不根据答案内容猜小问。另有 2024 Oct/Nov 21／23 的 `1(c)(i)`：QP 标签保留，MS 确实印作 `1(c)`，通过显式 `official_answer_label` 记录。工具只允许缺失首个 roman 子问对应同父标签，拒绝覆盖实际存在的精确行或占用另一叶节点的行。见[批准输入](ms-parent-label-repairs.json)与[报告](ms-parent-label-report.json)。原官方图形和文字直接保留，不生成替代答案。

分类修复另绑定原教学判断指纹。课程决定只能解除明确的分类范围问题，不能清除分数、官方答案、缺页或裁切门禁。依赖主章节重新求闭包，Paper 4 始终保留 A2 考试身份。详见 [1.1 分类扩展](classification-1.1.md)。

这些是维护代理制作和源内容核对，不是独立人工逐题复核；保留原 `not_human_reviewed` 信息。不新增教师强制审核模块。

## 复现与恢复

使用已安装 `requirements.txt` 的 Python。将已发布 v0.5.1 的两个索引与 `teaching19-decisions.json` 放在 `data/baseline-v051/`，自行提供 `source_id → 本机 PDF 路径` 的私有 JSON。原始资料必须精确匹配已有 SHA-256。以下输出目录须不存在，不覆盖上次结果。

```sh
python scripts/repair_pending_edges.py --snapshot data/baseline-v051 \
  --sources data/source-files.private.json \
  --decisions data/baseline-v051/teaching19-decisions.json \
  --output data/edges --revision 2026-10-29.reliability.1
python scripts/repair_pending_ms.py --snapshot data/edges \
  --sources data/source-files.private.json \
  --decisions data/baseline-v051/teaching19-decisions.json \
  --approvals docs/reliability/ms-row-repairs.json \
  --output data/ms --revision 2026-10-29.reliability.2
python scripts/apply_organic_scope_extension.py --snapshot data/ms \
  --sources data/source-files.private.json --decisions data/ms/teaching19-decisions.json \
  --approvals docs/reliability/single-step-scope.json \
  --output data/scope --revision 2026-10-29.reliability.3
python scripts/apply_teaching_repairs.py --snapshot data/scope \
  --sources data/source-files.private.json --decisions data/scope/teaching19-decisions.json \
  --approvals docs/reliability/organic-teaching-repairs.json \
  --output data/repaired --revision 2026-10-29.reliability.4
python scripts/verify_reliability_update.py --previous data/baseline-v051 \
  --snapshot data/repaired --sources data/source-files.private.json \
  --output data/reliability-acceptance
python scripts/verify_bundled_repair_adoption.py --previous data/baseline-v051 \
  --snapshot data/repaired --released-full /path/to/actual-v051-FullBank.qbank \
  --output data/bundled-adoption-acceptance
```

修复命令只生成候选公开快照，不安装、不读取实际教师 profile。真实验收工具使用独立目录和开发版后端，复制合法本地原卷进行检查；不是已冻结 App 的安装验收。

第二批从上面的 `data/repaired` 继续，按下表顺序执行。每步 `--snapshot` 与 `--decisions` 指向上一步输出；MS 步使用 `repair_pending_ms.py`，其他步使用 `apply_teaching_repairs.py`，`--sources` 保持同一私有映射。输出目录仍须不存在。全部批准文件绑定具体旧指纹，不可跳步重用。

| 输出目录 | revision 后缀 | `--approvals docs/reliability/…` |
| --- | --- | --- |
| `data/foundations` | `reliability.5` | `foundation-teaching-repairs.json` |
| `data/ms-parent-labels` | `reliability.6` | `ms-parent-label-repairs.json` |
| `data/inorganic` | `reliability.7` | `inorganic-teaching-repairs.json` |
| `data/iodoform` | `reliability.8` | `iodoform-teaching-repairs.json` |
| `data/nitrogen` | `reliability.9` | `nitrogen-teaching-repairs.json` |

完整 revision 的共同前缀为 `2026-10-29.`。最终再以 `data/repaired` 为 `--previous`、`data/nitrogen` 为 `--snapshot` 运行接口验收；采用测试的 `--previous` 则继续使用已发布 v0.5.1 基线。当前机器报告分别对应这两种测试范围。

新快照包最低读取版本是 0.6.0，防止旧 App 误读分类 1.1 或再次拒绝已证明安全的字体框边界。不要将开发包当作 v0.5.1 更新附件。保留原 `.qbank` 事务备份／回滚；真实验收已验证旧作业、草稿、备注、分享顺序、局部人工校准字节一致，失败恢复及重复安装。新 App 只自动退役哈希精确匹配的已发布 v0.5.0／v0.5.1 激活快照，自定义版本继续保留。

回滚索引不回滚或清空个人作业。未正式采用新快照时直接保留旧文件即可；已安装开发更新时先退出 App，用现有 `scripts/import_bank.py rollback` 和安装返回的备份 ID 恢复公共题库。

## 实测与未完成项

第二批本地开发后端的 20 个选题单位为 20 问、34 分：学生卷 0.4338 秒、1,296,378 字节、14 页；答案卷 0.5941 秒、1,044,421 字节、35 页。44 个恢复单位共 139 个预览区域，冷缓存总计 3.7342 秒、热缓存 0.2106 秒。更新安装实测 50.3735 秒。测量不包括独立 App 的首次启动，不外推其他电脑性能。

第二批两组覆盖全部恢复单位的导出共 151 页，已全部渲染；抽查了分页概览与局部原题／答案，不声称独立人工逐页审核。第一批分页概览暴露的重复附加通用 MS 原则、周期表／常数表和印刷标记占页问题仍需处理。当前导出未完成节纸优化，不能把“每页有页眉文字”当作没有空白内容页的证明。它属于后续 Goal 3 的明确改进项。

剩余 241 个单位的原因可重叠，详见 JSON／CSV；其中 112 个仍受两份来源异常影响。尚待继续核查 MS 错标、重复标签、真实分值冲突及裁切边界。已解决此前没有主章节的全部分类边界，仍有材料问题的题没有因分类确认而放行。

Paper 5 初扫有 63 对文件名配对，包含 54 变体；这不是已经核验或入库的数量。教师已确认它采用独立的实验技能分类，并按实际考查内容附加化学章节标签。见[初始资料审计](paper5-initial-audit.json)与[项目审计](project-audit.md)。没有自动从第三方网站下载资料。
