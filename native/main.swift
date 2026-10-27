import Cocoa
import WebKit
import Darwin

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler, WKUIDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var process: Process?
    var base: URL?
    var pipe: Pipe?
    var startupTimer: Timer?
    var userHome: URL!
    var resources: URL!
    var instanceID = ""
    var outputBuffer = Data()
    let bufferLock = NSLock()
    var ready = false
    var probing = false
    var quitting = false
    var failed = false
    var testMode: Bool { ProcessInfo.processInfo.environment["QUESTION_SPACE_AUTOTEST"] == "1" }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let env = ProcessInfo.processInfo.environment
        if let override = env["QUESTION_BANK_HOME"] {
            userHome = URL(fileURLWithPath: override, isDirectory: true)
        } else {
            userHome = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("ChemistryWorkspace", isDirectory: true)
        }
        resources = Bundle.main.resourceURL!.appendingPathComponent("workspace", isDirectory: true)
        do { try FileManager.default.createDirectory(at: userHome.appendingPathComponent("data"), withIntermediateDirectories: true) }
        catch { showFailure("无法创建用户数据目录：\(error.localizedDescription)"); return }
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "native")
        web = WKWebView(frame: .zero, configuration: configuration)
        web.navigationDelegate = self; web.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 880),
            styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        let internalBuild = Bundle.main.object(forInfoDictionaryKey: "QuestionSpaceDistribution") as? String != "developer-id"
        window.title = "题间 · CIE AS Chemistry" + (internalBuild ? " · 内部测试（未公证）" : "")
        window.minSize = NSSize(width: 800, height: 600); window.contentView = web; window.center()
        window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        web.loadHTMLString("<html><meta charset='utf-8'><body style='font:18px -apple-system;padding:60px'>正在启动题间…<p>首次启动将建立本地题库。</p></body></html>", baseURL: nil)
        createMenu()
        startBackend()
    }

    func createMenu() {
        let menu = NSMenu(); let appItem = NSMenuItem(); let appMenu = NSMenu()
        appMenu.addItem(withTitle: "关于题间", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        let migrate = NSMenuItem(title: "从旧项目导入数据…", action: #selector(importOldProject), keyEquivalent: "")
        migrate.target = self; appMenu.addItem(migrate)
        let data = NSMenuItem(title: "打开用户数据目录", action: #selector(openDataDirectory), keyEquivalent: "")
        data.target = self; appMenu.addItem(data)
        let licenses = NSMenuItem(title: "许可与对应源码…", action: #selector(openLicenses), keyEquivalent: "")
        licenses.target = self; appMenu.addItem(licenses); appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出题间", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu; menu.addItem(appItem)
        let edit = NSMenuItem(); let editMenu = NSMenu(title: "编辑")
        for (title, selector, key) in [("撤销", "undo:", "z"), ("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            editMenu.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        edit.submenu = editMenu; menu.addItem(edit); NSApp.mainMenu = menu
    }

    func startBackend() {
        ready = false; probing = false; failed = false; instanceID = UUID().uuidString; base = nil
        outputBuffer = Data()
        let executable = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/QuestionBackend.app/Contents/MacOS/QuestionBackend")
        guard FileManager.default.isExecutableFile(atPath: executable.path) else {
            showFailure("安装包的内置后端缺失，请重新下载完整 DMG。无需安装 Python。"); return
        }
        let child = Process(); child.executableURL = executable
        child.arguments = ["--resources", resources.path, "--user-root", userHome.path,
                           "--instance-id", instanceID, "--parent-pid", String(getpid())]
        child.currentDirectoryURL = userHome
        var environment = ProcessInfo.processInfo.environment
        for key in ["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH", "QUESTION_BANK_ROOT", "QUESTION_BANK_RESOURCES", "QUESTION_BANK_DB", "QUESTION_BANK_PORT"] { environment.removeValue(forKey: key) }
        environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        child.environment = environment
        let output = Pipe(); pipe = output; child.standardOutput = output
        let log = userHome.appendingPathComponent("data/server.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
        if let handle = try? FileHandle(forWritingTo: log) { handle.seekToEndOfFile(); child.standardError = handle }
        output.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let bytes = handle.availableData
            guard let self = self, !bytes.isEmpty else { return }
            self.bufferLock.lock(); self.outputBuffer.append(bytes)
            var lines: [String] = []
            while let range = self.outputBuffer.range(of: Data([10])) {
                lines.append(String(decoding: self.outputBuffer[..<range.lowerBound], as: UTF8.self))
                self.outputBuffer.removeSubrange(..<range.upperBound)
            }
            self.bufferLock.unlock()
            for line in lines {
                if let url = URL(string: line), url.scheme == "http", url.host == "127.0.0.1", url.port != nil {
                    DispatchQueue.main.async { self.checkReadiness(url) }
                }
            }
        }
        child.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                guard let self = self, !self.quitting else { return }
                self.startupTimer?.invalidate()
                self.showFailure(self.ready ? "本地后端意外退出。已保存的作业仍在用户目录，可以重试启动。" : "内置后端未能启动。请查看用户目录 data/server.log。")
            }
        }
        do {
            try child.run(); process = child
            startupTimer = Timer.scheduledTimer(withTimeInterval: 60, repeats: false) { [weak self] _ in
                guard let self = self, !self.ready else { return }
                self.stopBackend(); self.showFailure("本地服务启动超时。用户数据未删除，请查看 data/server.log。")
            }
        } catch { showFailure("无法启动内置后端：\(error.localizedDescription)") }
    }

    func checkReadiness(_ url: URL) {
        guard !ready, !probing, !quitting else { return }; probing = true
        var request = URLRequest(url: url.appendingPathComponent("api/health")); request.timeoutInterval = 10
        URLSession.shared.dataTask(with: request) { [weak self] bytes, response, error in
            DispatchQueue.main.async {
                guard let self = self, !self.quitting else { return }
                guard let bytes = bytes, let http = response as? HTTPURLResponse, http.statusCode == 200,
                      let health = (try? JSONSerialization.jsonObject(with: bytes)) as? [String: Any],
                      health["instance_id"] as? String == self.instanceID,
                      health["pid"] as? Int == Int(self.process?.processIdentifier ?? 0), health["ready"] as? Bool == true else {
                    self.stopBackend(); self.showFailure("内置服务身份或就绪检查失败，请查看日志后重试。"); return
                }
                self.ready = true; self.base = url; self.startupTimer?.invalidate()
                self.web.load(URLRequest(url: url))
                // Automated native lifecycle tests observe health, not UI screenshots or developer tools.
                if self.testMode, let path = ProcessInfo.processInfo.environment["QUESTION_SPACE_READY_FILE"] {
                    var result = health; result["url"] = url.absoluteString
                    if let data = try? JSONSerialization.data(withJSONObject: result) { try? data.write(to: URL(fileURLWithPath: path), options: .atomic) }
                }
                if self.testMode, let seconds = ProcessInfo.processInfo.environment["QUESTION_SPACE_AUTO_QUIT_SECONDS"], let delay = Double(seconds) {
                    DispatchQueue.main.asyncAfter(deadline: .now() + delay) { NSApp.terminate(nil) }
                }
            }
        }.resume()
    }

    func stopBackend() {
        startupTimer?.invalidate(); pipe?.fileHandleForReading.readabilityHandler = nil
        guard let child = process else { return }; child.terminationHandler = nil
        if child.isRunning {
            child.terminate(); let deadline = Date().addingTimeInterval(4)
            while child.isRunning && Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if child.isRunning { kill(child.processIdentifier, SIGKILL); child.waitUntilExit() }
        }
        process = nil
    }
    func showFailure(_ text: String) {
        guard !failed, !quitting else { return }; failed = true
        if testMode { fputs(text + "\n", stderr); stopBackend(); NSApp.terminate(nil); return }
        let alert = NSAlert(); alert.messageText = "题间启动遇到问题"; alert.informativeText = text
        alert.addButton(withTitle: "重试"); alert.addButton(withTitle: "退出")
        if alert.runModal() == .alertFirstButtonReturn { stopBackend(); startBackend() } else { NSApp.terminate(nil) }
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { quitting = true; stopBackend() }
    @objc func openDataDirectory() { NSWorkspace.shared.open(userHome) }
    @objc func openLicenses() { NSWorkspace.shared.open(resources.appendingPathComponent("licenses")) }

    @objc func importOldProject() {
        guard let base = base else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        panel.message = "选择旧版题间项目目录。将复制数据并保留当前作业，不删除或覆盖旧文件。"
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let folder = panel.url else { return }
            var request = URLRequest(url: base.appendingPathComponent("api/import-project")); request.httpMethod = "POST"
            request.timeoutInterval = 300; request.setValue("1", forHTTPHeaderField: "X-Local-Request")
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: ["path": folder.path])
            URLSession.shared.dataTask(with: request) { data, response, error in
                DispatchQueue.main.async {
                    let json = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
                    let ok = (response as? HTTPURLResponse)?.statusCode == 200
                    let alert = NSAlert(); alert.messageText = ok ? "旧项目数据已复制" : "旧项目导入失败"
                    alert.informativeText = ok ? "新增作业：\(json?["jobs_added"] ?? 0)；原卷：\(json?["sources_added"] ?? 0)。冲突项目未覆盖，完整报告保存在用户目录 data/imports 中。" : (json?["error"] as? String ?? error?.localizedDescription ?? "请检查日志")
                    alert.beginSheetModal(for: self.window) { _ in if ok { self.web.reload() } }
                }
            }.resume()
        }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert(); alert.messageText = message; alert.addButton(withTitle: "继续"); alert.addButton(withTitle: "取消")
        alert.beginSheetModal(for: window) { completionHandler($0 == .alertFirstButtonReturn) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        decisionHandler((url.scheme == "about" || (url.host == "127.0.0.1" && url.port == base?.port)) ? .allow : .cancel)
    }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.canChooseFiles = true; panel.canChooseDirectories = false; panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.beginSheetModal(for: window) { completionHandler($0 == .OK ? panel.urls : nil) }
    }
    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, let origin = message.frameInfo.request.url,
              origin.host == "127.0.0.1", origin.port == base?.port, let dict = message.body as? [String: String] else { return }
        if dict["action"] == "importOldProject" { importOldProject(); return }
        if dict["action"] == "open", let path = dict["url"], let base = base, (path.hasPrefix("/source/") || path.hasPrefix("/exports/")), let url = URL(string: path, relativeTo: base), url.host == base.host, url.port == base.port {
            URLSession.shared.dataTask(with: url) { data, response, error in
                guard let data = data, (response as? HTTPURLResponse)?.statusCode == 200 else { return }
                let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".pdf")
                do { try data.write(to: file); DispatchQueue.main.async { NSWorkspace.shared.open(file) } } catch { }
            }.resume()
        }
        if dict["action"] == "saveText", let text = dict["text"] {
            let panel = NSSavePanel(); panel.nameFieldStringValue = "作业方案.ciepaper"
            panel.beginSheetModal(for: window) { response in
                if response == .OK, let url = panel.url { try? text.write(to: url, atomically: true, encoding: .utf8) }
            }
        }
    }
}
let app = NSApplication.shared
let delegate = AppDelegate(); app.delegate = delegate; app.setActivationPolicy(.regular); app.run()
