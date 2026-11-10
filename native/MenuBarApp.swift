import AppKit
import WebKit

final class IntakeDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    private var item: NSStatusItem!
    private let popover = NSPopover()
    private var web: WKWebView!
    private var starting = false
    private var root: URL {
        URL(fileURLWithPath: Bundle.main.object(forInfoDictionaryKey: "DJIntakeProjectRoot") as! String)
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        configureMenus()
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = item.button {
            button.image = NSImage(systemSymbolName: "opticaldisc", accessibilityDescription: "DJ Intake")
            button.image?.isTemplate = true
            button.toolTip = "DJ Intake — quick add a track"
            button.target = self
            button.action = #selector(togglePanel)
            button.setAccessibilityLabel("DJ Intake quick add")
        }
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "intake")
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 390, height: 380), configuration: configuration)
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        let controller = NSViewController()
        controller.view = web
        popover.contentViewController = controller
        popover.contentSize = NSSize(width: 390, height: 380)
        popover.behavior = .transient
        let quick = CommandLine.arguments.contains("--quick")
        prepare(openBrowser: !quick, showPanel: quick)
    }

    private func configureMenus() {
        let bar = NSMenu()
        let appRoot = NSMenuItem()
        let appMenu = NSMenu(title: "DJ Intake")
        appMenu.addItem(withTitle: "Quit DJ Intake menu bar", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appRoot.submenu = appMenu
        bar.addItem(appRoot)
        let editRoot = NSMenuItem()
        let edit = NSMenu(title: "Edit")
        for (title, action, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        editRoot.submenu = edit
        bar.addItem(editRoot)
        NSApp.mainMenu = bar
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        prepare(openBrowser: true)
        return true
    }

    private func prepare(openBrowser: Bool, showPanel: Bool = false) {
        guard !starting else { return }
        starting = true
        let process = Process()
        process.executableURL = root.appendingPathComponent(".venv/bin/python")
        process.arguments = [root.appendingPathComponent("scripts/launch.py").path] + (openBrowser ? [] : ["--no-browser"])
        process.currentDirectoryURL = root
        let pipe = Pipe()
        process.standardError = pipe
        process.standardOutput = FileHandle.nullDevice
        process.standardInput = FileHandle.nullDevice
        process.terminationHandler = { [weak self] task in
            let details = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.starting = false
                if task.terminationStatus == 0 {
                    self.web.load(URLRequest(url: URL(string: "http://127.0.0.1:8765/quick")!))
                    if showPanel { self.showPanel() }
                } else {
                    let alert = NSAlert()
                    alert.messageText = "DJ Intake could not start"
                    alert.informativeText = details.isEmpty ? "Reopen the app or check the app log." : details
                    alert.runModal()
                }
            }
        }
        do { try process.run() }
        catch {
            starting = false
            let alert = NSAlert()
            alert.messageText = "DJ Intake could not start"
            alert.informativeText = error.localizedDescription
            alert.runModal()
        }
    }

    @objc private func togglePanel() {
        if popover.isShown { popover.performClose(nil) }
        else { prepare(openBrowser: false, showPanel: true) }
    }

    private func showPanel() {
        guard let button = item.button else { return }
        NSApp.activate(ignoringOtherApps: true)
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame,
              message.frameInfo.request.url?.host == "127.0.0.1",
              message.frameInfo.request.url?.port == 8765,
              let data = message.body as? [String: Any], let action = data["action"] as? String else { return }
        switch action {
        case "resize":
            if let height = data["height"] as? Double {
                popover.contentSize = NSSize(width: 390, height: max(300, min(760, height)))
            }
        case "open":
            popover.performClose(nil)
            // Only the fixed tutorial page is allowed besides the library home.
            if data["path"] as? String == "/?tour", let tour = URL(string: "http://127.0.0.1:8765/?tour") {
                NSWorkspace.shared.open(tour)
            } else {
                prepare(openBrowser: true)
            }
        case "quit":
            NSApp.terminate(nil)
        default: break
        }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let url = navigationAction.request.url
        decisionHandler(url?.host == "127.0.0.1" && url?.port == 8765 ? .allow : .cancel)
    }
}

if let index = CommandLine.arguments.firstIndex(of: "--choose-folder") {
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    let panel = NSOpenPanel()
    panel.title = "DJ Intake"
    panel.message = "Choose your default download folder"
    panel.prompt = "Choose"
    panel.canChooseDirectories = true
    panel.canChooseFiles = false
    panel.canCreateDirectories = true
    if CommandLine.arguments.count > index + 1 {
        panel.directoryURL = URL(fileURLWithPath: CommandLine.arguments[index + 1])
    }
    app.activate(ignoringOtherApps: true)
    if panel.runModal() == .OK, let url = panel.url {
        print(url.path)
        exit(0)
    }
    exit(2)
}

let app = NSApplication.shared
let delegate = IntakeDelegate()
app.delegate = delegate
app.run()
