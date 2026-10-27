# Portable Question Coordinate Index 1.0.0

此规范独立于题间 UI、SQLite、Python 和任何 PDF 库。公开数据由 `indexes/question-index.json` 和 `indexes/source-manifest.json` 组成；JSON 使用 UTF-8，JSON Schema 采用 Draft 2020-12。字段名大小写有意义。

## 坐标契约

`coordinate_system` 必须为 `pdf-point-unrotated-cropbox-top-left-v1`。

1. 单位是 PDF point，1 point = 1/72 inch。与 DPI、浏览器缩放、Retina 和缩略图分辨率无关。1.0.0 只支持 `/UserUnit = 1`；其他单位拒绝导入，不能擅自缩放坐标。
2. `page_index` 为 PDF 物理页序，从 0 开始，不是印刷页码。
3. `bbox` 为 `[x0, y0, x1, y1]`，满足 `0 <= x0 < x1 <= width`、`0 <= y0 < y1 <= height`。
4. 坐标原点为**有效 CropBox 在未旋转页面上的左上角**；x 向右、y 向下。有效 CropBox 是原始 CropBox 与 MediaBox 的交集。
5. Source Manifest 每页记录原生 PDF 坐标下的 `media_box` 和有效 `crop_box`。这两个 box 使用 PDF 原生坐标（x 向右、y 向上，原点不保证为零），不是题目 bbox 的坐标系统。`width`、`height` 是未旋转 CropBox 的尺寸。`rotation` 记录原始 `/Rotate`（0、90、180、270）。这些字段是坐标的参考几何，随源文件 SHA-256 固定。
6. 若原生 PDF 点为 `(X,Y)`，CropBox 为 `[cx0,cy0,cx1,cy1]`，则规范点为 `(X-cx0, cy1-Y)`。原生矩形 `[X0,Y0,X1,Y1]` 转换为 `[X0-cx0,cy1-Y1,X1-cx0,cy1-Y0]`。**此时不应用 `/Rotate`**。
7. 读取器先建立不旋转的 CropBox 局部页面，再按 bbox 提取。若某库的页面图像已旋转，必须先逆变换到上述规范空间。题间的 PyMuPDF 适配器只在内存中将 page rotation 置零；从不把这个状态保存回原卷。
8. regions 数组顺序就是阅读与排版顺序。跨页或同页多个语义块都使用多个 region；不能把不连续内容当成长图任意切割。题目和答案各自拥有独立 source_id。

浮点数按 JSON number 表示；不要反复四舍五入。机器检查容差为 0.01 point，仅用于 PDF 浮点尺寸误差，不允许将越界区域静默裁小。

## Source Manifest

必填顶层：`schema_version`、`coordinate_system`、`sources`。每个 source 包含：

| 字段 | 类型 | 含义 |
|---|---|---|
| source_id | string | 不变的内容版本身份；不使用数据库行号 |
| filename | string | 识别提示，不作为内容正确性的依据 |
| path | string | 相对于项目根目录的 POSIX 路径；禁止绝对路径、父目录跳转、盘符和反斜线 |
| sha256 | string | 原始 PDF 字节的 64 位小写十六进制 SHA-256 |
| page_count | integer | 物理页数 |
| pages | array | 按 page_index 连续排列的页面几何 |
| metadata | object | 可扩展的来源身份、role、参考数据区域、来源说明等 |

CIE 示例：`cie-9701-2024-m-12-qp`、`cie-9701-2024-m-12-ms`。同一个 source_id 不可在更新时悄悄指向不同 SHA-256；修订文件应创建新的带版本后缀的 source_id 并显式迁移引用。路径可改变，内容身份不变。旧 CIE1 分享仍使用 filename → hash；若引入同名异版源应为新版设不同 filename，避免分享歧义。

`metadata.references` 为可选附录区域数组，元素含 `page_index`、`bbox`、`rotate`；坐标仍遵循同一契约。rotate 仅用于附录的输出朝向。这里只存区域，不存周期表或评分原则原文。

## Question Index

顶层必填：`schema_version`、`coordinate_system`、`bank_id`、`revision`、`topics`、`questions`。revision 是资料修订标识，不是 schema 版本。

每题包含：`question_id`、`exam_board`、`qualification`、`subject_code`、`year`、`session`、`paper`、`variant`、`original_question_number`、`marks`、`topics`、`question`、`answer`、`metadata`。

- 推荐新 ID：`cie-9701-2024-m-12-q01`。本项目保留已经发布的 `cie-9701-m24-12-q1`，不重命名，确保原有作业和分享可用。ID 一经发布不可重新分配给其他题。建议组件使用小写 ASCII 与连字符，schema 允许 `[A-Za-z0-9._:-]` 以容纳其他考试体系。
- paper 为卷别整数（如 1），variant 为变体整数（如 2），两者组合才是原卷 12；原题号为字符串，可表达 `1(a)(ii)`，不要求纯数字。qualification、exam_board、subject_code 不枚举锁死，可以扩展到 Edexcel、AQA、Physics、Maths。
- marks 为非负 number 或 null（尚未确认），不可猜测未知分值。
- topics 为多个稳定 topic ID，引用顶层 topics 定义。建议分类与考纲点不是一回事。
- question 含 source_id 和至少一个 region。answer 含 `type: mcq | regions`、独立 source_id 和至少一个 region；mcq 可选 value（A/B/C/D），但公开 CIE 索引不嵌入答案值。题间在用户导入原卷后，仅在本机数据库提取字母答案；不明确时用 MS 区域代替。
- metadata 允许扩展。当前使用 review_status、classification_basis、syllabus_version、syllabus_mapping_status、granularity、migration_status。`pending_review` 不等于复核通过；旧年份不因分类而自动符合新考纲。未来可在 metadata 中增加精确 syllabus statement 版本、依赖题 ID 与复核证据。

顶层和标准字段对象禁止未知字段；扩展放入 metadata，不私自改变已有字段语义。JSON 不包含本机绝对路径、原题全文、图片、评分原文或 Base64 PDF。

## 版本与验证

schema_version 使用 SemVer。1.0.0 实现只接受明确支持的 1.0.0；未知版本拒绝打开，不猜测兼容。对外规范的 patch 只修正文档/校验缺陷，minor 可增加明确的可选字段，major 才能改变坐标语义或必填字段。未来版本必须提供显式转换器，不能只改版本字符串。已有数字版旧索引由 `bank.migration` 转换：页码减一、字段规范化、哈希和几何核验，稳定题 ID 保留。

```sh
python scripts/bank_tool.py validate
python scripts/bank_tool.py validate --index examples/question-index.example.json --manifest examples/source-manifest.example.json
```

jsonschema 检查类型与结构；验证工具进一步检查 ID 唯一、相对路径、引用完整性、考试身份对应、页面几何、bbox 边界及附录区域。导入／读取时再核验实际文件 SHA-256 和页面几何。结构通过不代表题目边界和答案内容已经独立复核。

原创示例可独立重建：`python examples/create_example.py --output /tmp/question-example`。其中包含跨页、CropBox 偏移、旋转、结构化答案示例；生成的 PDF 是原创测试材料，不是 Cambridge 真题。

## 版权边界

索引仅描述来源身份、几何区域和编者分类；原卷、原题图形、考纲与评分内容不随公开分发。用户自行导入合法获取的原始文件。源码 MIT 许可不授予考试材料权利。公开索引也不能被解释为权利人允许重分发试卷或商业使用。
