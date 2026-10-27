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
