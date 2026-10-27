import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKScriptMessageHandler, WKUIDelegate {
 var window:NSWindow!; var web:WKWebView!; var process:Process?; var base:URL!; var project:URL!; var pipe:Pipe!
 func applicationDidFinishLaunching(_ notification:Notification){
  project=Bundle.main.bundleURL.deletingLastPathComponent()
  let config=WKWebViewConfiguration();config.userContentController.add(self,name:"native")
  web=WKWebView(frame:.zero,configuration:config);web.navigationDelegate=self;web.uiDelegate=self
  window=NSWindow(contentRect:NSRect(x:0,y:0,width:1320,height:880),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
  window.title="题间 · CIE AS Chemistry";window.minSize=NSSize(width:800,height:600);window.contentView=web;window.center();window.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
  let menu=NSMenu();let item=NSMenuItem();let submenu=NSMenu();submenu.addItem(withTitle:"关于题间",action:#selector(NSApplication.orderFrontStandardAboutPanel(_:)),keyEquivalent:"");submenu.addItem(.separator());submenu.addItem(withTitle:"退出题间",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q");item.submenu=submenu;menu.addItem(item)
  let edit=NSMenuItem();let editMenu=NSMenu(title:"编辑");for (title,selector,key) in [("撤销","undo:","z"),("剪切","cut:","x"),("复制","copy:","c"),("粘贴","paste:","v"),("全选","selectAll:","a")]{editMenu.addItem(withTitle:title,action:Selector(selector),keyEquivalent:key)};edit.submenu=editMenu;menu.addItem(edit);NSApp.mainMenu=menu
  let py=project.appendingPathComponent("runtime.json")
  guard let data=try? Data(contentsOf:py),let settings=(try? JSONSerialization.jsonObject(with:data)) as? [String:String],let executable=settings["python"] else{fail("缺少 runtime.json，请在项目目录运行 scripts/build_app.sh。");return}
  let p=Process();p.executableURL=URL(fileURLWithPath:executable);p.arguments=[project.appendingPathComponent("app/server.py").path];p.currentDirectoryURL=project;pipe=Pipe();p.standardOutput=pipe
  let log=project.appendingPathComponent("data/server.log");FileManager.default.createFile(atPath:log.path,contents:nil);p.standardError=try? FileHandle(forWritingTo:log)
  var started=false
  pipe.fileHandleForReading.readabilityHandler={ handle in
   let bytes=handle.availableData
   guard !bytes.isEmpty,let text=String(data:bytes,encoding:.utf8),let line=text.split(separator:"\n").first,let url=URL(string:String(line)),url.host=="127.0.0.1" else{return}
   DispatchQueue.main.async {if !started{started=true;self.base=url;self.web.load(URLRequest(url:url))}}
  }
  p.terminationHandler={_ in DispatchQueue.main.async {if NSApp.isRunning && !started{self.fail("本地服务未能启动。请查看 data/server.log，或运行启动.command 检查 Python 环境。")}}}
  do{try p.run();process=p}catch{fail("无法启动 Python：\(error.localizedDescription)")}
 }
 func fail(_ text:String){let a=NSAlert();a.messageText="启动遇到问题";a.informativeText=text;a.runModal()}
 func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool{true}
 func applicationWillTerminate(_ notification:Notification){pipe?.fileHandleForReading.readabilityHandler=nil;process?.terminationHandler=nil;process?.terminate()}
 func webView(_ webView:WKWebView,runJavaScriptConfirmPanelWithMessage message:String,initiatedByFrame frame:WKFrameInfo,completionHandler:@escaping(Bool)->Void){let a=NSAlert();a.messageText=message;a.addButton(withTitle:"继续");a.addButton(withTitle:"取消");a.beginSheetModal(for:window){completionHandler($0 == .alertFirstButtonReturn)}}
 func webView(_ webView:WKWebView,decidePolicyFor navigationAction:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void){guard let url=navigationAction.request.url else{decisionHandler(.cancel);return};decisionHandler(url.host=="127.0.0.1" && url.port==base?.port ? .allow:.cancel)}
 func userContentController(_ userContentController:WKUserContentController,didReceive message:WKScriptMessage){
  guard message.frameInfo.isMainFrame,message.frameInfo.request.url?.host=="127.0.0.1",let dict=message.body as? [String:String] else{return}
  if dict["action"]=="open",let path=dict["url"]{
   let name=URL(fileURLWithPath:path).lastPathComponent
   let file:URL
   if path.hasPrefix("/exports/"),name.hasSuffix(".pdf"){file=project.appendingPathComponent("exports").appendingPathComponent(name)}
   else if path.hasPrefix("/source/"),name.hasSuffix(".pdf"){file=project.appendingPathComponent("data/sources").appendingPathComponent(name)}else{return}
   NSWorkspace.shared.open(file)
  }
  if dict["action"]=="saveText",let text=dict["text"]{let panel=NSSavePanel();panel.nameFieldStringValue="作业方案.ciepaper";panel.beginSheetModal(for:window){response in if response == .OK,let url=panel.url{do{try text.write(to:url,atomically:true,encoding:.utf8)}catch{self.fail(error.localizedDescription)}}}}
 }
}
let app=NSApplication.shared
let delegate=AppDelegate();app.delegate=delegate;app.setActivationPolicy(.regular);app.run()
