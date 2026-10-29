# 可靠性重构：第一批可复现修复

这是 v0.6 开发过程中的 Goal 1 检查点，不是整个工作台目标已经完成，也不是已发布的新安装包。稳定下载仍是 v0.5.1。Paper 5、剩余待整理题及教师工作流／PDF 排版优化继续进行。

## 当前结果

以提交 `e5afa5baa28a1db63f1100666202cdbab02bb99b` 的 v0.5.1 公开快照为基线。

| 范围 | 原可用／待整理 | 本批可用／待整理 |
| --- | ---: | ---: |
| Paper 1 | 2280／0 | 2280／0 |
| Paper 2 | 2109／68 | 2124／53 |
| Paper 4 | 3277／264 | 3309／232 |
| 合计 | 7666／332 | 7713／285 |

全部 7,998 个稳定 ID 和 352 份来源的 ID、路径、哈希保留。没有修改任何原始 PDF。13 个 AS 小问重新定位了官方 MS 区域；其他本批变动没有移动题目或答案坐标。

47 个恢复单位的顺序互斥统计：

1. 字体边界框误报重新验证，以及相应前问解除隔离：15 个。
2. 旧式 MS 标签已能被现有解析器精确识别，重新测量并阅读确认：13 个。
3. 教师确认臭氧化／环加成可归第 11 章后，材料检查同时通过：4 个。
4. 教师确认有机立体异构／普通羰基还原的章节规则后，材料检查同时通过：15 个。

另外有 29 个原来已经可用的有机小问按确认后的教学规则改归第 11 章；不是新增题量。8 个臭氧化／环加成问、46 个有机立体异构／还原问均保留带材料指纹的决定记录；有缺页或裁切异常的继续待整理。

教师已进一步确认其余基础有机归第 11 章。这个规则的后续批次仍在核查，不计入上表的 47 个恢复单位；没有更改尚未实际处理题目的状态。

[总报告](checkpoint.json) · [全部待整理 JSON](pending.json) · [CSV](pending.csv) · [材料接口验收](source-acceptance.json)。`docs/paper4/` 和 `docs/teaching19/` 原来的 v0.5.1／v0.5.0 报告保留为历史基线，不将历史发布数值改写为本次开发数值。

完整自动测试 139 项通过，无跳过，实测 32.650 秒，包含设置本地 `CIE_CORPUS` 的真实样本回归。全部 7,998 条公开判断的材料指纹重新核对一致，公开索引不嵌入选择题官方答案。实际已发布快照的四类升级检查见[基础／完整包采用测试](bundled-adoption.json)。

## 两份集中异常原卷

| 原卷 | PDF 页树／实际页数 | 封面声明 | 本地未找到的印刷页 |
| --- | ---: | ---: | --- |
| 2024 May/June 43 | 25／25 | 28 | 26、27、28 |
| 2026 March 42 | 23／23 | 28 | 2、17、26、27、28 |

两份 PDF 打开时均未触发 MuPDF 的修复模式，页树计数与实际读取一致。不是当前 PDF 读取器简单少算了页；本地文件不含上述声明页。尚未取得足够证据证明它们全部是空白或非必需内容，因此原有 57＋55 个单位继续保留来源完整性门禁。全部识别分值均为 100 不能替代这个检查。

详细印刷页与源 SHA-256 在 [裁切检查报告的 source_audits](edge-repair-report.json)。不能把另一变体的附页当作本变体原页，也不能填造缺失坐标或修改既有源哈希。

## 修复方式和质量边界

`crop_edges.py` 只处理字体框穿越边界的情况：把落在裁切框外的字体框区域变换回规范的未旋转坐标，按 288 dpi 渲染，只有整块没有可见墨迹才排除该误报。像素格向外取整；遇到文字、化学键等墨迹、越界或无法测量时保持警报。它不移动裁切线，不忽略实际缺页，也不证明某个完全未纳入裁图的上下文已经齐全。

MS 修复要求同时满足：旧材料指纹、明确的图文核对记录、重新测得的答案指纹、精确完整小问标签、分数相等、QP／MS 几何与边界检查。旧 `3(b)(iii)` 被错误并入后续紧凑 `3c(i)` 的评分内容等情况，按新边界分别恢复；不根据答案内容猜小问。原官方图形和文字直接保留，不生成替代答案。

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

新快照包最低读取版本是 0.6.0，防止旧 App 误读分类 1.1 或再次拒绝已证明安全的字体框边界。不要将开发包当作 v0.5.1 更新附件。保留原 `.qbank` 事务备份／回滚；真实验收已验证旧作业、草稿、备注、分享顺序、局部人工校准字节一致，失败恢复及重复安装。新 App 只自动退役哈希精确匹配的已发布 v0.5.0／v0.5.1 激活快照，自定义版本继续保留。

回滚索引不回滚或清空个人作业。未正式采用新快照时直接保留旧文件即可；已安装开发更新时先退出 App，用现有 `scripts/import_bank.py rollback` 和安装返回的备份 ID 恢复公共题库。

## 实测与未完成项

本地开发后端的 20 个选题单位自动补全为 21 问、32 分：学生卷 0.4252 秒、2,182,581 字节、11 页；答案卷 0.4076 秒、995,814 字节、28 页。47 个恢复单位共 159 个预览区域，冷缓存总计 4.0636 秒、热缓存 0.2113 秒。更新安装实测 45.0964 秒。测量不包括独立 App 的首次启动，不外推其他电脑性能。

两组覆盖全部恢复单位的导出共 161 页，已渲染用于分页概览；局部原题／答案图另行核对。分页概览暴露了重复附加通用 MS 原则、周期表／常数表和印刷标记占页的问题。当前导出未完成节纸优化，不能把“每页有页眉文字”当作没有空白内容页的证明。它属于后续 Goal 3 的明确改进项。

剩余 285 个单位的原因可重叠，详见 JSON／CSV；其中 112 个仍受两份来源异常影响。尚待继续核查 MS 错标、重复标签、真实分值冲突、裁切边界及没有已确认教学归属的题目。未知归属继续向教师询问；不凭关键词放行。

Paper 5 初扫有 63 对文件名配对，包含 54 变体；这不是已经核验或入库的数量。见[初始资料审计](paper5-initial-audit.json)与[项目审计](project-audit.md)。没有自动从第三方网站下载资料。
