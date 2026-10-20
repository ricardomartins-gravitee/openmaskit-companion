import AppKit
import CompanionDesktopCore
import SwiftUI

struct Service: Codable, Identifiable {
    var id: String { name }
    let name: String
    let state: String
    let health: String
    var title: String {
        switch name {
        case "openmaskit": return "OpenMaskit"
        case "presidio-analyzer": return "Presidio"
        default: return "Local MCP connection"
        }
    }
}

struct Installation: Codable {
    var initialized = false
    var paired = false
    var services: [Service] = []
    var connectors: [ConnectorState]?
    var error: String?
}

struct ConnectorState: Codable, Identifiable {
    let id: String
    let name: String
    let connected: Bool
}

struct LocalProfile: Codable, Identifiable {
    let id: String
    let name: String
}

@MainActor final class CompanionModel: ObservableObject {
    @Published var installation = Installation()
    @Published var profiles: [LocalProfile] = []
    @Published var busy = false
    @Published var message = ""
    @Published var connectorRunning = false
    private var connector: Process?
    private var monitor: Task<Void, Never>?

    func startMonitoring() {
        guard monitor == nil else { return }
        monitor = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .seconds(5))
            }
        }
    }

    var backend: URL {
        if let development = ProcessInfo.processInfo.environment["COMPANION_BACKEND"] {
            return URL(fileURLWithPath: development)
        }
        return Bundle.main.resourceURL!.appendingPathComponent("backend/openmaskit-companion/openmaskit-companion")
    }

    var baseArguments: [String] {
        if let home = ProcessInfo.processInfo.environment["COMPANION_HOME"] {
            return ["--home", home]
        }
        return []
    }

    var releaseImage: String? {
        guard let path = Bundle.main.url(forResource: "release", withExtension: "json"),
              let data = try? Data(contentsOf: path),
              let manifest = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return manifest["companion_image"] as? String
    }

    func invoke(_ arguments: [String], input: Data? = nil) async throws -> Data {
        let executable = backend
        let allArguments = baseArguments + arguments
        return try await Task.detached {
            let process = Process()
            let output = Pipe(), errors = Pipe(), incoming = Pipe()
            process.executableURL = executable
            process.arguments = allArguments
            process.standardOutput = output
            process.standardError = errors
            process.standardInput = incoming
            try process.run()
            if let input { incoming.fileHandleForWriting.write(input) }
            try? incoming.fileHandleForWriting.close()
            process.waitUntilExit()
            guard process.terminationStatus == 0 else {
                throw NSError(domain: "Companion", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "The action could not finish. Check Docker Desktop, pairing and your local MCP settings."])
            }
            return output.fileHandleForReading.readDataToEndOfFile()
        }.value
    }

    func refresh() async {
        guard !busy else { return }
        do {
            installation = try JSONDecoder().decode(Installation.self, from: await invoke(["status"]))
            let data = try await invoke(["profiles"])
            struct ProfileList: Codable { let profiles: [LocalProfile] }
            profiles = try JSONDecoder().decode(ProfileList.self, from: data).profiles
        } catch { message = error.localizedDescription }
    }

    func action(_ arguments: [String], success: String) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            _ = try await invoke(arguments)
            message = success
            installation = try JSONDecoder().decode(Installation.self, from: await invoke(["status"]))
        } catch { message = error.localizedDescription }
    }

    func pair() async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            struct Pairing: Codable { let code: String }
            let data = try await invoke(["pairing-code", "--name", Host.current().localizedName ?? "My Mac"])
            let code = try JSONDecoder().decode(Pairing.self, from: data).code
            _ = try await invoke(["pair", "--code-stdin"], input: Data((code + "\n").utf8))
            installation.paired = true
            message = "This Mac is paired. You can connect your approved MCPs."
        } catch { message = error.localizedDescription }
    }

    func toggleConnector() {
        if connectorRunning { stopConnector(); return }
        let process = Process()
        process.executableURL = backend
        process.arguments = baseArguments + ["connect"]
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.terminationHandler = { [weak self] _ in
            Task { @MainActor in self?.connectorRunning = false }
        }
        do {
            try process.run()
            connector = process
            connectorRunning = true
            message = "Connector started. Connection status appears below."
        } catch { message = "The local connector could not start." }
    }

    func stopConnector() {
        connector?.terminate()
        connector = nil
        connectorRunning = false
    }

    func approve() {
        let panel = NSOpenPanel()
        panel.title = "Choose a local MCP profile"
        panel.allowedContentTypes = [.json]
        panel.canChooseDirectories = false
        guard panel.runModal() == .OK, let url = panel.url,
              let data = try? Data(contentsOf: url),
              let profile = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let command = profile["command"] as? String else {
            message = "Choose a JSON profile containing an absolute executable path."
            return
        }
        let alert = NSAlert()
        alert.messageText = "Approve this local MCP?"
        let arguments = (profile["args"] as? [String] ?? []).joined(separator: " ")
        alert.informativeText = "Executable: \(command)\nArguments: \(arguments)\n\nThis program runs with your account's permissions. Review its profile before approval. Environment values remain private."
        let field = NSTextField(string: "my-mcp")
        field.frame = NSRect(x: 0, y: 0, width: 300, height: 24)
        alert.accessoryView = field
        alert.addButton(withTitle: "Approve")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let id = field.stringValue
        Task {
            await action(["approve", id, "--name", id, "--profile", url.path, "--yes"], success: "MCP approved. Restart the connector to apply changes.")
            await refresh()
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    var model: CompanionModel?
    var preferences: AppPreferences?
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag || preferences?.mainWindowClosed == true {
            preferences?.revealMainWindow()
        }
        return false
    }
    func applicationWillTerminate(_ notification: Notification) {
        MainActor.assumeIsolated { model?.stopConnector() }
    }
}

@main struct CompanionApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject var model = CompanionModel()
    @StateObject var preferences = AppPreferences()

    var body: some Scene {
        Window("OpenMaskit Companion", id: "main") {
            VStack(alignment: .leading, spacing: 22) {
                HStack(alignment: .top) {
                    Image(systemName: "desktopcomputer.and.arrow.down")
                        .font(.system(size: 30)).foregroundStyle(.blue)
                    VStack(alignment: .leading, spacing: 5) {
                        Text("OpenMaskit Companion").font(.largeTitle.bold())
                        Text("Your local services and MCP connections").foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text("Development alpha").font(.caption).padding(7)
                        .background(.orange.opacity(0.12), in: Capsule())
                }
                GroupBox("Services") {
                    VStack(alignment: .leading, spacing: 12) {
                        if !model.installation.initialized {
                            Text("Set up a separate OpenMaskit installation with Presidio. Your existing services remain available.")
                            Button("Set Up OpenMaskit") {
                                if let image = model.releaseImage {
                                    Task { await model.action(["setup", "--image", image], success: "Installation prepared. Choose Start Services.") }
                                } else { model.message = "This development build needs a published relay image. See the source setup instructions." }
                            }
                        } else {
                            ForEach(model.installation.services) { service in
                                HStack {
                                    Circle().fill(service.health == "healthy" ? .green : .gray).frame(width: 8, height: 8)
                                    Text(service.title)
                                    Spacer()
                                    Text(service.health.isEmpty ? service.state : service.health).foregroundStyle(.secondary)
                                }
                            }
                            if model.installation.services.isEmpty { Text("Services are stopped.").foregroundStyle(.secondary) }
                            HStack {
                                Button("Start Services") { Task { await model.action(["start"], success: "Services are ready.") } }
                                Button("Stop Services") { Task { await model.action(["stop"], success: "Services stopped. Your settings are saved.") } }
                                Spacer()
                                Button("Open OpenMaskit") { NSWorkspace.shared.open(URL(string: "http://127.0.0.1:9493")!) }
                            }
                        }
                    }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                }
                GroupBox("Local MCPs") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(model.installation.paired ? "This Mac is paired with your local OpenMaskit installation." : "Pair this Mac, then approve the MCPs it can run.")
                            .foregroundStyle(.secondary)
                        HStack {
                            Button(model.installation.paired ? "Pair Again" : "Pair This Mac") { Task { await model.pair() } }
                                .disabled(!model.installation.initialized)
                            Button("Add Local MCP…") { model.approve() }
                            Spacer()
                            Button(model.connectorRunning ? "Stop Connector" : "Start Connector") { model.toggleConnector() }
                                .disabled(!model.installation.paired)
                        }
                        ForEach(model.profiles) { profile in
                            HStack {
                                Image(systemName: "checkmark.shield").foregroundStyle(.green)
                                Text(profile.name)
                                Spacer()
                                Button("Add to OpenMaskit") {
                                    Task { await model.action(["register", profile.id, "--name", profile.name], success: "MCP added. Configure its checks in OpenMaskit.") }
                                }.disabled(!model.connectorRunning)
                            }
                        }
                        ForEach(model.installation.connectors ?? []) { connector in
                            Label(connector.name + (connector.connected ? " · Connected" : " · Offline"),
                                  systemImage: connector.connected ? "link" : "link.badge.plus")
                                .font(.callout).foregroundStyle(connector.connected ? .green : .secondary)
                        }
                    }.padding(10).frame(maxWidth: .infinity, alignment: .leading)
                }
                HStack {
                    Image(systemName: "arrow.triangle.2.circlepath")
                    Text("Updates are manual in this development build.").foregroundStyle(.secondary)
                    Spacer()
                    Button("Refresh") { Task { await model.refresh() } }
                    SettingsLink { Text("Settings…") }
                }.font(.callout)
                if model.busy { ProgressView("Working…").controlSize(.small) }
                if let error = model.installation.error { Text(error).foregroundStyle(.orange) }
                if !model.message.isEmpty { Text(model.message).font(.callout).textSelection(.enabled) }
            }
            .padding(28).frame(minWidth: 680, minHeight: 520)
            .disabled(model.busy)
            .background(MainWindowObserver(preferences: preferences))
            .onAppear {
                delegate.model = model
                delegate.preferences = preferences
                model.startMonitoring()
            }
        }
        .windowResizability(.contentSize)
        Settings { SettingsScreen(preferences: preferences) }
        MenuBarExtra("OpenMaskit Companion", systemImage: "shield.lefthalf.filled", isInserted: Binding(
            get: { preferences.menuBarVisible },
            // SwiftUI echoes insertion state while synchronizing scenes. Only
            // Settings changes the preferences; publishing the echo loops and
            // would turn close-only visibility into a permanent menu-bar option.
            set: { preferences.synchronizeMenuBarInsertion($0) })) {
            CompanionMenu(model: model, preferences: preferences)
        }.menuBarExtraStyle(.menu)
    }
}
