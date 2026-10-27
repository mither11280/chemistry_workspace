# 命令与失败恢复

在仓库根执行。`--resources` 是全局参数，应放在子命令前。默认基础数据是 `indexes/`，已发布更新应以该 generation 目录为 `--base`。

```sh
python scripts/import_bank.py analyze /path/to/pdfs --workdir data/import-work/batch1 --revision 2026-10-27.batch1
python scripts/import_bank.py analyze /path/to/pdfs --workdir data/import-work/batch1 --revision 2026-10-27.batch1 --overrides data/import-work/repairs.json
python scripts/import_bank.py package --workdir data/import-work/batch1 --output dist/batch1.qbank --changelog '新增卷别；修复某题标签'
python scripts/import_bank.py install dist/batch1.qbank --home /path/to/test-profile --sha256 <打印出的包哈希>
python scripts/import_bank.py rollback <安装结果中的backup_id> --home /path/to/test-profile
```

`analyze` 不修改已安装目录。输出包含可公开的两个坐标 JSON、计数报告，以及仅供本地维护的 `cache/`、`source-files.private.json`、`quarantine.json`（候选坐标、异常与源指纹）。解析缓存包含原题文字；不要公开或混入程序源码包。

逐题修正文件是以稳定 ID 为键的对象：

```json
{
  "cie-9701-s22-22-q1": {
    "source_fingerprint": "report.json对应pair的64位指纹",
    "topics": ["atomic", "bonding"],
    "reason": "根据该题原文修正主题建议"
  }
}
```

可选修正字段为完整 `question`、完整 `answer`、`marks`、`topics`、`reason`。question/answer 使用现有坐标规范，不能更换源身份。错误指纹或多余字段直接报错；无效区域仍被隔离。全卷锚点/总分失败不能通过逐题 patch 豁免，需要修复解析器并增加回归样例、提升 parser 版本；缓存自动失效。题号可以由 MS 交叉核对，但不能以答案替代缺失题干。

若需附原卷，添加 `--include-sources --authorization data/import-work/rights.json`。授权记录格式：

```json
{"redistribution_authorized":true,"statement":"维护者确认本批次资料在实际授权范围内可以再分发","sha256":["每个附带PDF的64位SHA256"]}
```

授权声明是维护者记录，不等于软件授予版权许可。试卷保持原版权。未知授权不得填 true。

更新包仅含完整索引快照、manifest、update.json、可选 `sources/**/*.pdf`。SHA-256 检测损坏，不证明发布者身份；通过维护者可信发布地址分发并提供包哈希。App 安装前展示 revision、说明及哈希，用户确认后切换 generation。旧 generation 和备份保留；回滚不恢复/覆盖个人作业。新原卷即使激活失败也可以安全留存，不删除用户文件。

引擎限制：无 OCR、无 LLM 自动评分/考纲精确映射；关键词置信值只是支持度。几何/文字边缘检查不能证明化学结构式语义完整。目录中同身份不同哈希隔离；相同哈希副本去重。只选所需批次文件，避免把同一试卷不同扫描版本混在一起。

## 2018–2026 历年扩充

先做覆盖清单，不把实际缺卷、取消考试和未结束考季混在一起：

```sh
python scripts/import_bank.py inventory /path/to/9701 --base /path/to/current-public-snapshot --output data/import-work/inventory
python scripts/expand_9701_bank.py --corpus /path/to/9701 --base /path/to/current-public-snapshot --output data/import-work/history --revision-prefix 2026-10-27.history
```

批次顺序为 2022–2025 未入库卷 → 2026 已取得成对卷 → 2018–2021。支持 `--phase modern|year2026|legacy`，单阶段重试时 `--base` 指向该阶段之前的公开快照；不重做其他阶段。重复运行复用按原卷哈希、策略及 parser version 缓存的解析。已有稳定 ID 按完整考试身份匹配；不要把数据库自增 ID 当公开 ID。

`inventory.json`/CSV 保存年度、考季、卷别、variant、QP/MS 是否发现、原题数、原哈希、既有入库及 QA。`coverage.json` 和 `anomalies.json` 为本轮实际结果；`final/` 是可交换完整快照。各阶段快照分别使用前一阶段精确 revision，最终阶段快照也用于累计整合包，保证安装路径最终收敛到同一 revision。

同身份不同哈希默认冲突。仅在未旋转页面的 boxes、全部文字位置与全部页面 RGB 像素完全相同的情况下，允许判定内容重复（显示 `/Rotate` 可以不同）；为新考试身份选择一份文件，保留所有哈希及选择记录。已经登记的源哈希始终优先，不因重复副本改写 source_id。部分删页或课堂改写副本不参与这种合并。

旧版策略必须给 Section B 的每道题附上原卷共用答题编码表；答案表与多页 MS 按阅读布局分析，再逆变换到未旋转 CropBox 坐标。2026 的 Guidance 是说明栏，不可把里面的数字加进分值。对新版式的改动需要相应合成和真实本地样本回归。

原考纲周期与当前考纲兼容性分开：旧题无法逐条确认时保持 unknown，宽泛知识点对应当前章节只是候选。具体文档修订号不确定时保留 null。2020 May/June 标为取消考季公开练习材料；2026 Oct/Nov 未完成期间即使目录中有文件也不发布。

历史题库包使用 `--minimum-app-version 0.4.0`，因为旧阅读方向、文字编码和 Guidance 校验需要新版后端。坐标 JSON 仍是 schema 1.0.0。附资料时除了逐文件 SHA-256 授权清单，可填写 `exam_years` 约束真实年份；具体原卷必须同时满足哈希及年份范围。维护者授权记录应如实注明来源是用户确认，不能伪造成权利人证书。

实际打包、隔离目录安装、预览、混排组卷、回滚及个人作业字节一致性，可用 `scripts/verify_historical_bank.py`；它需要已有许可清单，不自动生成授权、不下载第三方 PDF，也不访问真实教师 profile。
