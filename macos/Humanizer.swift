import AppKit
import Foundation
import Darwin

enum ServiceError: Error { case connection, protocolError, pathTooLong }

func serviceRequest(_ object: [String: Any], root: URL) throws -> [String: Any] {
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { throw ServiceError.connection }
    defer { Darwin.close(fd) }
    var noSignal: Int32 = 1
    setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &noSignal, socklen_t(MemoryLayout<Int32>.size))
    var timeout = timeval(tv_sec: 8, tv_usec: 0)
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    let bytes = Array(root.appendingPathComponent("control.sock").path.utf8CString)
    guard bytes.count <= MemoryLayout.size(ofValue: address.sun_path) else { throw ServiceError.pathTooLong }
    withUnsafeMutableBytes(of: &address.sun_path) { target in
        for (index, byte) in bytes.enumerated() { target[index] = UInt8(bitPattern: byte) }
    }
    address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
    let connected = withUnsafePointer(to: &address) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    guard connected == 0 else { throw ServiceError.connection }
    var data = try JSONSerialization.data(withJSONObject: object)
    data.append(10)
    try data.withUnsafeBytes { buffer in
        var offset = 0
        while offset < buffer.count {
            let count = Darwin.write(fd, buffer.baseAddress!.advanced(by: offset), buffer.count - offset)
            guard count > 0 else { throw ServiceError.connection }
            offset += count
        }
    }
    var response = Data()
    var buffer = [UInt8](repeating: 0, count: 8192)
    while response.count < 2 * 1024 * 1024 {
        let count = Darwin.read(fd, &buffer, buffer.count)
        guard count > 0 else { throw ServiceError.connection }
        response.append(contentsOf: buffer.prefix(count))
        if response.last == 10 { break }
    }
    guard let result = try JSONSerialization.jsonObject(with: response) as? [String: Any] else {
        throw ServiceError.protocolError
    }
    return result
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let root: URL = {
        if let path = ProcessInfo.processInfo.environment["HUMANIZER_DATA_DIR"] {
            return URL(fileURLWithPath: path)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Humanizer")
    }()
    let queue = DispatchQueue(label: "humanizer.menu-service")
    var controller: Process?
    var statusItem: NSStatusItem!
    var statusLine: NSMenuItem!
    var memoryLine: NSMenuItem!
    var toggle: NSMenuItem!
    var enabled = false
    var checking = false
    var timer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.button?.image = NSImage(systemSymbolName: "text.bubble", accessibilityDescription: "Humanizer")
        statusItem.button?.setAccessibilityLabel("Humanizer")
        statusItem.button?.toolTip = "Humanizer: starting"
        let menu = NSMenu()
        menu.autoenablesItems = false
        menu.delegate = self
        let title = NSMenuItem(title: "Humanizer", action: nil, keyEquivalent: "")
        title.isEnabled = false
        menu.addItem(title)
        statusLine = NSMenuItem(title: "Starting…", action: nil, keyEquivalent: "")
        statusLine.isEnabled = false
        menu.addItem(statusLine)
        memoryLine = NSMenuItem(title: "Model memory: —", action: nil, keyEquivalent: "")
        memoryLine.isEnabled = false
        menu.addItem(memoryLine)
        menu.addItem(.separator())
        toggle = NSMenuItem(title: "Enabled", action: #selector(toggleEnabled), keyEquivalent: "")
        toggle.target = self
        toggle.isEnabled = false
        menu.addItem(toggle)
        menu.addItem(.separator())
        let logs = NSMenuItem(title: "Open Logs…", action: #selector(openLogs), keyEquivalent: "")
        logs.target = self
        menu.addItem(logs)
        let quit = NSMenuItem(title: "Quit Humanizer", action: #selector(quitApp), keyEquivalent: "q")
        quit.target = self
        menu.addItem(quit)
        statusItem.menu = menu
        startController()
        timer = Timer(timeInterval: 4, repeats: true) { [weak self] _ in self?.refresh() }
        timer?.tolerance = 2
        RunLoop.main.add(timer!, forMode: .common)
    }

    func startController() {
        queue.async { [self] in
            do {
                if let existing = try? serviceRequest(["action": "status"], root: root) {
                    DispatchQueue.main.async { self.render(existing) }
                    return
                }
                let configData = try Data(contentsOf: root.appendingPathComponent("config.json"))
                guard let config = try JSONSerialization.jsonObject(with: configData) as? [String: Any],
                      let python = config["python"] as? String,
                      let resources = Bundle.main.resourceURL else { throw ServiceError.protocolError }
                let process = Process()
                process.executableURL = URL(fileURLWithPath: python)
                process.arguments = ["-m", "humanizer_mcp.controller", "--data-dir", root.path,
                                     "--parent-pid", String(ProcessInfo.processInfo.processIdentifier)]
                process.currentDirectoryURL = root
                var env = ProcessInfo.processInfo.environment
                env["PYTHONPATH"] = resources.appendingPathComponent("python").path
                env["PYTHONUNBUFFERED"] = "1"
                env["PYTHONDONTWRITEBYTECODE"] = "1"
                env["HF_HUB_OFFLINE"] = "1"
                process.environment = env
                let logURL = root.appendingPathComponent("controller.log")
                if !FileManager.default.fileExists(atPath: logURL.path) {
                    FileManager.default.createFile(atPath: logURL.path, contents: nil,
                                                  attributes: [.posixPermissions: 0o600])
                }
                let log = try FileHandle(forWritingTo: logURL)
                try log.seekToEnd()
                process.standardOutput = log
                process.standardError = log
                process.standardInput = FileHandle.nullDevice
                try process.run()
                DispatchQueue.main.async { self.controller = process }
                for _ in 0..<40 {
                    if let status = try? serviceRequest(["action": "status"], root: root) {
                        DispatchQueue.main.async { self.render(status) }
                        return
                    }
                    Thread.sleep(forTimeInterval: 0.25)
                }
                throw ServiceError.connection
            } catch {
                DispatchQueue.main.async {
                    self.statusLine.title = "Could not start. Check installation and logs."
                    self.statusItem.button?.toolTip = "Humanizer: unavailable"
                    self.toggle.isEnabled = false
                }
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        // Opening the app again should reveal its controls, even though it has no windows.
        // Use the run loop, not a main-queue block, so menu tracking can receive status updates.
        perform(#selector(showMenu), with: nil, afterDelay: 0)
        return false
    }

    @objc func showMenu() { statusItem.button?.performClick(nil) }

    func menuWillOpen(_ menu: NSMenu) { refresh() }

    func refresh() {
        guard !checking else { return }
        checking = true
        queue.async { [self] in
            let status = try? serviceRequest(["action": "status"], root: root)
            DispatchQueue.main.async {
                self.checking = false
                if let status { self.render(status) }
                else {
                    self.statusLine.title = "Service unavailable. Reopen Humanizer."
                    self.toggle.isEnabled = false
                    self.statusItem.button?.appearsDisabled = true
                }
            }
        }
    }

    func render(_ value: [String: Any]) {
        enabled = value["enabled"] as? Bool ?? false
        toggle.state = enabled ? .on : .off
        toggle.isEnabled = true
        let state = value["status"] as? String ?? "error"
        let message = value["message"] as? String ?? "Unavailable"
        statusLine.title = message
        let memory = (value["active_bytes"] as? Double ?? 0) + (value["cache_bytes"] as? Double ?? 0)
        memoryLine.title = memory > 0 ? String(format: "Model memory: %.1f GB", memory / 1_000_000_000)
                                    : "Model memory: unloaded"
        if state == "loading" { memoryLine.title = "Model memory: loading…" }
        statusItem.button?.appearsDisabled = !enabled
        let symbol = state == "busy" ? "pencil.line" : (state == "loading" ? "arrow.triangle.2.circlepath" : "text.bubble")
        statusItem.button?.image = NSImage(systemSymbolName: symbol, accessibilityDescription: "Humanizer")
        statusItem.button?.toolTip = "Humanizer: \(message)"
    }

    @objc func toggleEnabled() {
        toggle.isEnabled = false
        let desired = !enabled
        statusLine.title = desired ? "Loading model…" : "Unloading model…"
        queue.async { [self] in
            let status = try? serviceRequest(["action": "enable", "enabled": desired], root: root)
            DispatchQueue.main.async {
                if let status { self.render(status) }
                else { self.statusLine.title = "Could not change state. Reopen Humanizer." }
            }
        }
    }

    @objc func openLogs() { NSWorkspace.shared.open(root) }
    @objc func quitApp() { NSApp.terminate(nil) }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        timer?.invalidate()
        queue.async { [self] in
            _ = try? serviceRequest(["action": "enable", "enabled": false], root: root)
            DispatchQueue.main.async {
                if self.controller?.isRunning == true { self.controller?.terminate() }
                sender.reply(toApplicationShouldTerminate: true)
            }
        }
        return .terminateLater
    }
}

let app = NSApplication.shared
if let bundleID = Bundle.main.bundleIdentifier,
   NSRunningApplication.runningApplications(withBundleIdentifier: bundleID)
       .contains(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier }) {
    exit(0)
}
let delegate = AppDelegate()
app.delegate = delegate
app.run()
