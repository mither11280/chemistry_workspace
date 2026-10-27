# 安装包许可审查（2026-10-27）

这是分发工程审查，不是原权利人授权或法律意见。开发者必须为所分发的实际组件和数据确认权利边界。

## MIT 与 AGPL

项目原创源码原有 MIT 许可保持不变，MIT 并不是所有打包内容的统一许可。

PyMuPDF 1.26.5 / MuPDF 采用 AGPL-3.0 或 Artifex 商业许可。PyInstaller 的 bootloader 例外不豁免第三方依赖的许可条件。把本软件源码以 MIT 开源，并不自动免除捆绑 PyMuPDF/MuPDF 的 AGPL 义务，也不能将整个二进制安装包宣传为 MIT-only 或闭源可随意使用。

当前构建默认按 AGPL 路径准备：保留所有原有许可与版权说明；将应用完整可修改源码和构建/安装脚本放入 AppSource；Release 同时提供 CorrespondingSource（含分别核对过的精确版本 PyMuPDF、MuPDF 及其他运行时依赖源代码归档、许可和下载哈希清单）。应用原创 MIT 文件仍保留 MIT 权利与声明；分发与组合产生的义务按 AGPL-3.0 遵守。若不接受 AGPL 路径，必须取得覆盖产品分发的 Artifex 商业许可，再明确配置发行许可；不能通过把 Python 移到 helper 进程就假定获得豁免。

源代码获取不能只靠一条可能失效的上游网页链接代替。在公开提供二进制下载的位置，也要提供对应源码下载。重建所需具体构建步骤、依赖版本和 source manifest 随包提供。自行修改 PyMuPDF/MuPDF 或替换二进制后，必须更新源码归档以匹配实际分发版本。

## 其他依赖

- Python：PSF 许可及其包含的历史许可；不是 MIT。
- Pillow：HPND/MIT-CMU 风格许可；wheel 中附有 WebP、JPEG、TIFF、FreeType 等组件的版权和许可，整体复制保留。
- jsonschema / attrs / referencing / rpds-py / jsonschema-specifications：分别保留各发行版附带的 MIT 或其他许可文件。
- PyInstaller：GPL-2.0-or-later 加 bootloader 分发例外，部分文件 Apache-2.0；它的例外允许打包应用，但不重新许可 PyMuPDF。
- Apple Cocoa/WebKit 系统框架不复制入包，使用操作系统提供的框架。

实际版本及提取的许可文件位于 `Contents/Resources/workspace/licenses/`。构建输出提供 inventory，源码下载使用发布者元数据的 SHA-256 校验。不要把依赖增加或版本替换视为无需重新审查的操作。

## Cambridge 数据

按本次要求，当前安装包包含 2024–2026 March 9701 Paper 12/22 的 QP/MS 及相关考纲。文件哈希与既有 Source Manifest 完全一致，原文件不修改，首次启动复制到用户 Application Support。

这些 PDF 是独立的受版权保护材料，不归 MIT 或 AGPL 许可。维护者于 2026-10-27 在本任务中明确确认已取得这些资料的再分发授权，允许公开发布含资料的安装包；该确认记录在 packaging/exam-distribution.json。这是维护者的权利陈述，并非本工具签发的授权证明，也没有把这些材料改为开源许可。源码仓库仍不跟踪这些 PDF。对外发布含资料 DMG 前，发布者须确认再分发权；CI 公开发布步骤要求单独确认这一点。不能用“内部测试”“教育用途”或“开源”代替版权许可。

## 官方依据

- PyMuPDF 双许可：[官方文档](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
- Artifex 分发许可：[PyMuPDF Licensing](https://pymupdf.io/licensing)
- AGPL-3.0：[GNU 正文](https://www.gnu.org/licenses/agpl-3.0.html)
- PyInstaller bootloader 例外：[官方说明](https://pyinstaller.org/en/stable/license.html)

没有商业许可证或其他证据时，构建脚本不会宣称商业许可或统一 MIT 许可。未经 Developer ID 和公证的包也不会被标成正式受信任发行版。
