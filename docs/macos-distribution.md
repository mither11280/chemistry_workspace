# macOS 独立安装包

## 普通用户

下载 arm64 DMG，打开后把「题间.app」拖到 Applications。打开应用即可使用，解释器、PyMuPDF、Pillow、SQLite、JSON Schema 和 WebP 编解码都在包内。无需 Python、pip、Swift、Xcode 或终端。当前最低 macOS 13，Apple Silicon arm64；不提供 Intel/Universal 安装包。

包中包含v0.5.2 Source Manifest 对应的 352 个原始 PDF（Paper 1／2／4 QP/MS、考纲和 Data Booklet），首次启动按哈希校验并复制到用户目录，7,757 个可用选题单位可直接预览、组卷。它们是独立版权数据，不受软件 MIT/AGPL 许可授权，见许可审查。

文件名含 `INTERNAL-UNNOTARIZED`：这是 ad-hoc 内部测试包，没有 Developer ID、没有 Apple 公证。Gatekeeper 可能拒绝首次启动；不能把它称为正式可信发行版。正式用户的“下载后双击即用”发行需要成功签名、公证、staple 和 Gatekeeper 验证。脚本不会自动移除 quarantine 或指导禁用 Gatekeeper 来伪造这一验收。

## 数据位置与升级

```text
~/Library/Application Support/ChemistryWorkspace/
  sources/                    原卷副本，每个内容版本一份
  data/personal.sqlite3       个人作业、草稿
  data/catalog.sqlite3        本地题库及全文索引
  data/*.local.json           个人校准/来源扩展
  data/cache/webp/            可删除缓存
  data/backups/               迁移、版本升级前备份
  data/imports/               旧项目快照、导入报告
  data/server.log             后端日志
  exports/                    生成的作业 PDF 与题号映射
```

新版本只替换 Applications 中的 App，不替换用户目录。静态资源在 App 的 Resources/workspace 中只读使用；原卷首次复制时不覆盖已有不同内容。版本变更前，数据库使用 SQLite backup API 做快照，保存本机 JSON 校准；升级不会清除原卷或个人作业。

旧版项目：菜单「题间 → 从旧项目导入数据…」选择整个旧项目目录。先复制原始文件/元数据、用 SQLite backup 捕获数据库，再导入匹配原卷及作业。原目录不移动或删除；ID 冲突但内容不同的作业生成副本，当前草稿保持不变，旧草稿作为命名作业保存。重复导入用内容指纹去重。同 ID 不同坐标或来源版本冲突的项目保留当前数据，原数据仍在快照里并记录报告。未知旧 PDF 题保留 legacy 支持，不从裁片猜坐标。

## 包结构与后端生命周期

```text
题间.app/Contents/
  MacOS/QuestionSpace                 Swift + WKWebView
  Helpers/QuestionBackend.app/        PyInstaller COLLECT (onedir) + BUNDLE
    Contents/MacOS/QuestionBackend    内置后端可执行文件
    Contents/Frameworks/              libpython、扩展模块、MuPDF/Pillow 动态库
    Contents/Resources/               PyInstaller 管理的 Python 资源
  Resources/workspace/
    app/                             HTML/CSS/JS
    indexes/ schemas/                 公共索引和格式规范
    bundled-sources/                  原始 QP/MS/考纲，不来自开发者绝对路径
    licenses/                         许可、依赖清单、应用源码归档
    build-info.json                   版本、架构、签名类别和文件哈希
```

Swift 不读取 runtime.json，不查询 Python PATH。它启动固定 bundle-relative helper，传入只读资源和 Application Support 路径。后端随机绑定 127.0.0.1，Swift 校验 health 的实例 UUID/PID 后才加载页面；超时/异常退出给出日志入口和重试。正常退出 terminate + 有界等待；父进程异常消失时 helper 的 parent watchdog 也会退出，防止遗留服务。个人数据目录有单实例后端文件锁。

## 开发者构建

构建机需要 arm64 macOS、Python 3.12 和 Xcode Command Line Tools。**这些仅是构建工具，不是用户安装前置条件。**

```sh
python3.12 -m venv .packaging-venv
source .packaging-venv/bin/activate
pip install -r requirements-build.txt
python scripts/collect_corresponding_source.py --version 0.2.0 --prepare-only
./scripts/build_app.sh --version 0.2.0 --exam-source-dir /path/to/local/sources
python scripts/collect_corresponding_source.py --version 0.2.0
python scripts/verify_macos_distribution.py dist/ChemistryWorkspace-0.2.0-arm64-INTERNAL-UNNOTARIZED.dmg
```

构建默认要求所有 manifest PDF 存在且 SHA-256 相符，不会偷偷做缺卷安装包或从第三方爬取考试资料。只复制清单中的文件，个人数据库、缓存、作业或未知 PDF 不进入包。输出在 dist/，先前 App 构建移动到 build/macos/previous-app-* 保留。

## Developer ID 与公证

真实证书的构建：`./scripts/build_app.sh --sign-identity "Developer ID Application: ..."`。没有可用证书时默认 internal-adhoc；显式给定无效身份会失败，不能悄悄回落为正式版。

```sh
python scripts/notarize_macos.py dist/题间.app --identity "Developer ID Application: ..." --keychain-profile YOUR_STORED_NOTARY_PROFILE
```

也支持 App Store Connect `.p8` + key ID + issuer。脚本先提交 App ZIP，要求 Accepted，staple/validate App；再从已 staple 的 App 重建 DMG，签名、提交并 staple/validate DMG，最后执行 spctl 和深度签名校验。只在真实 Accepted 时生成 notarization-report.json。当前开发机没有 Developer ID，因此这条认证路径的成功结果尚未获得；测试包不宣称通过。

所有代码由内到外签名。保持 PyInstaller 的 Frameworks/Resources 布局，不把动态库放进任意资源目录，不用仅 `codesign --deep` 来代替逐层签名。默认不添加关闭库校验、允许未签名代码或关闭沙盒等宽泛 entitlements；若 Apple 对实际组件提出要求，须针对日志修正后重测。

## GitHub Actions / Release

`.github/workflows/macos-release.yml`：

1. PR/main 在全新 macos-14 arm64 runner 上运行 Python 3.12 回归测试。
2. workflow_dispatch 构建安装包，从维护者指定的 seed Release DMG 获取已经明确登记的 PDF，不抓取第三方题库；第一份 seed 可由本机已验证 DMG 作为 draft/internal Release 上传。
3. 有 Developer ID secrets 时临时导入证书和公证 Key，否则产出显式内部测试包。
4. 收集对应源码，实际挂载 DMG、复制到隔离 Applications、空 PATH/用户目录启动原生壳，验证 API、导出、退出、重开及升级。
5. artifact 保留 30 天；公开发布需要 `publish=true` 和对 Cambridge 再分发权的明确确认。签名版发布还要求真实公证报告。内部包为 prerelease，不伪装正式版。

可配置 secrets：CODESIGN_IDENTITY、MACOS_CERTIFICATE_P12（Base64）、MACOS_CERTIFICATE_PASSWORD、NOTARY_KEY_P8、NOTARY_KEY_ID、NOTARY_ISSUER_ID。凭据仅写到 runner 临时目录，退出时清理，不进入源码、App、DMG 或日志。源仓库仍忽略所有 PDF/DMG/证书/用户数据；Release 附件与源码仓库分开管理。

## 验证范围

`audit_macos_bundle.py` 检查每个 Mach-O 的 arm64、动态库/rpath 和最低系统要求，拒绝开发者绝对库路径及外部符号链接。

`verify_macos_distribution.py` 测试真实 DMG，不以目录存在充当安装成功：挂载只读镜像、确认 Applications 拖拽链接、复制 App 到临时目录、使用无 Python 搜索路径的环境从无关 cwd 启动；校验 frozen sys.path 全在 App 内，执行查询、QP 导入、WebP、学生卷与答案卷、保存/分享、退出后无子进程、替换版本后重开数据和原卷仍在，且 App 目录哈希未变。

升级测试以实际 App 替换和版本号变化模拟下一版，不能证明所有未来不兼容 schema 都能自动迁移。测试宿主并未物理卸载系统 Python；通过隔离环境、内部模块路径及 dyld 依赖审计证明 App 不依赖宿主解释器。Gatekeeper 的正式下载验收仍以签名、公证、quarantine 场景和目标系统的真实结果为准。

## 参考

- [PyInstaller macOS 布局与签名](https://pyinstaller.org/en/v6.16.0/feature-notes.html#macos-multi-arch-support)
- [Apple 公证流程](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [GitHub arm64 runner](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
