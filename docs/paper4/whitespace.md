# 外围留白收紧

坐标仍是未旋转 CropBox 左上角 PDF point，页码从 0 起，`bbox=[x0,y0,x1,y1]`。算法 `outer-vertical-ink-and-geometry-v2-answer-space-guard` 只改变 y0/y1；左右边界和原文内容流均不修改。

每一区域同时检查非空文字边界、矢量路径与线宽、图片边界、包含注释的灰度渲染。保护范围外保留约 6 point；另行渲染拟移除的上下边带确认没有可见墨迹。无法证明纯空白的区域、整个空白区域和存在阅读旋转的区域保持原坐标。

题目内部的空白、作图框、网格、答题线及末尾分数保留。无横线的答题空间通常由其末尾分数保护完整高度。另有语义保护：若分数紧跟作图、计算等题干指令，而下方仍有大块无横线空间，则保留原下边界；没有末尾分数的跨页作答区域也保守保留。不会通过扫描内部空白并拼接的方式压缩题目。条码等带有墨迹的边带不会被当作纯空白删除。

`scripts/trim_teaching_whitespace.py` 在新目录生成索引、逐区域证明及前后材料指纹，原索引和原卷不覆盖。只有原判定指纹与输入完全匹配时才可将判定迁移到证明等价的新材料。缓存版本 `webp-crop-layout-v4-answer-space-guard` 及区域信息一起使旧缩略图失效。

官方 MS 校验允许原始测得区域或可再次独立计算出的同一外围留白修正区域。任意缩小答案区域、丢失整行或裁掉评分内容仍会失败。正式导出继续从原 PDF 引用矢量区域，WebP 仅供浏览。

维护者可重现命令：

```sh
python scripts/trim_teaching_whitespace.py --snapshot INDEX_DIR --sources PRIVATE_SOURCE_MAP --output NEW_DIR --decisions DECISIONS_JSON --candidates PRIVATE_CANDIDATES_JSON
python scripts/audit_paper4_parts.py --snapshot INDEX_DIR --sources PRIVATE_SOURCE_MAP --output AUDIT_JSON
```

截图类型的实际样例是 `cie-9701-s18-11-q30`：底部边界由 792.703 改为 444.701 point，横坐标保持 25–575 point，谱图和全部选项保留。样例图和原题内容只置于本地验收目录及获得授权的发布附件，不嵌入公共坐标 JSON。
