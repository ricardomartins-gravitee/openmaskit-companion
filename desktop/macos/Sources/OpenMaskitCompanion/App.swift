import AppKit
import CompanionDesktopCore
import CompanionPolicy
import SwiftUI

typealias Installation = InstallationState

struct LocalProfile: Codable, Identifiable {
  let id: String
  let name: String
}

@MainActor final class CompanionModel: ObservableObject {
  @Published var installation = Installation()
  @Published var profiles: [LocalProfile] = []
  @Published var busy = false
  @Published var hasLoaded = false
  @Published var progress = ""
  private var refreshing = false
  private var configurationGeneration = 0
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
    return Bundle.main.resourceURL!.appendingPathComponent(
      "backend/openmaskit-companion/openmaskit-companion")
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
      let output = Pipe()
      let errors = Pipe()
      let incoming = Pipe()
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
        let failure =
          try? JSONSerialization.jsonObject(
            with: errors.fileHandleForReading.readDataToEndOfFile()) as? [String: String]
        let safeCodes = [
          "invalid_url", "unavailable", "not_openmaskit", "database_unavailable",
          "invalid_selection", "external_installation", "not_configured", "docker_unavailable",
        ]
        let detail = failure.flatMap { safeCodes.contains($0["code"] ?? "") ? $0["error"] : nil }
        throw NSError(
          domain: "Companion", code: 1,
          userInfo: [
            NSLocalizedDescriptionKey: detail
              ?? "The action could not finish. Check Docker Desktop, pairing and your local MCP settings."
          ])
      }
      return output.fileHandleForReading.readDataToEndOfFile()
    }.value
  }

  func refresh() async {
    guard !busy && !refreshing else { return }
    refreshing = true
    defer { refreshing = false }
    let generation = configurationGeneration
    do {
      let state = try JSONDecoder().decode(Installation.self, from: await invoke(["status"]))
      let data = try await invoke(["profiles"])
      struct ProfileList: Codable { let profiles: [LocalProfile] }
      let list = try JSONDecoder().decode(ProfileList.self, from: data)
      guard generation == configurationGeneration && !busy else { return }
      installation = state
      profiles = list.profiles
      hasLoaded = true
    } catch {
      guard generation == configurationGeneration && !busy else { return }
      installation.ready = false
      message = error.localizedDescription
    }
  }

  func connectExisting(_ address: String) async {
    guard !busy else { return }
    busy = true
    configurationGeneration += 1
    progress = "Checking your existing OpenMaskit installation…"
    message = ""
    defer {
      busy = false
      progress = ""
    }
    do {
      _ = try await invoke(["connect-existing", "--url", address])
      stopConnector()
      installation = try JSONDecoder().decode(Installation.self, from: await invoke(["status"]))
      hasLoaded = true
      message = "Connected. Your existing rules and settings stay in OpenMaskit."
    } catch { message = error.localizedDescription }
  }

  func configureManaged() async {
    guard !busy else { return }
    guard let image = releaseImage else {
      message = "This development build needs a verified service release."
      return
    }
    busy = true
    configurationGeneration += 1
    progress = "Checking Docker and preparing your installation…"
    message = ""
    defer {
      busy = false
      progress = ""
    }
    do {
      _ = try await invoke(["prepare-managed", "--image", image])
      stopConnector()
      progress = "Downloading and starting services. The first download can take several minutes…"
      installation = try JSONDecoder().decode(Installation.self, from: await invoke(["start"]))
      hasLoaded = true
      message =
        installation.canOpenDashboard
        ? "OpenMaskit is ready." : "Services are not ready yet. Retry setup in Settings."
    } catch {
      message = error.localizedDescription
      if let data = try? await invoke(["status"]),
        let state = try? JSONDecoder().decode(Installation.self, from: data)
      {
        installation = state
        hasLoaded = true
      }
    }
  }

  func openDashboard() async {
    guard !busy && installation.canOpenDashboard else { return }
    busy = true
    configurationGeneration += 1
    progress = "Checking OpenMaskit…"
    defer {
      busy = false
      progress = ""
    }
    do {
      struct Dashboard: Decodable {
        let dashboard: String
        let ready: Bool
      }
      let response = try JSONDecoder().decode(Dashboard.self, from: await invoke(["dashboard"]))
      guard response.ready, let url = Installation.localDashboardURL(response.dashboard) else {
        return
      }
      NSWorkspace.shared.open(url)
    } catch {
      installation.ready = false
      message = error.localizedDescription
    }
  }

  func action(_ arguments: [String], success: String) async {
    guard !busy else { return }
    busy = true
    configurationGeneration += 1
    message = ""
    defer { busy = false }
    do {
      _ = try await invoke(arguments)
      installation = try JSONDecoder().decode(Installation.self, from: await invoke(["status"]))
      message =
        arguments.first == "start" && !installation.ready
        ? "Services need attention. Check their status in Settings." : success
    } catch { message = error.localizedDescription }
  }

  func pair() async {
    guard !busy else { return }
    busy = true
    configurationGeneration += 1
    defer { busy = false }
    do {
      struct Pairing: Codable { let code: String }
      let data = try await invoke([
        "pairing-code", "--name", Host.current().localizedName ?? "My Mac",
      ])
      let code = try JSONDecoder().decode(Pairing.self, from: data).code
      _ = try await invoke(["pair", "--code-stdin"], input: Data((code + "\n").utf8))
      installation.paired = true
      message = "This Mac is paired. You can connect your approved MCPs."
    } catch { message = error.localizedDescription }
  }

  func toggleConnector() {
    if connectorRunning {
      stopConnector()
      return
    }
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
      let command = profile["command"] as? String
    else {
      message = "Choose a JSON profile containing an absolute executable path."
      return
    }
    let alert = NSAlert()
    alert.messageText = "Approve this local MCP?"
    let arguments = (profile["args"] as? [String] ?? []).joined(separator: " ")
    alert.informativeText =
      "Executable: \(command)\nArguments: \(arguments)\n\nThis program runs with your account's permissions. Review its profile before approval. Environment values remain private."
    let field = NSTextField(string: "my-mcp")
    field.frame = NSRect(x: 0, y: 0, width: 300, height: 24)
    alert.accessoryView = field
    alert.addButton(withTitle: "Approve")
    alert.addButton(withTitle: "Cancel")
    guard alert.runModal() == .alertFirstButtonReturn else { return }
    let id = field.stringValue
    Task {
      await action(
        ["approve", id, "--name", id, "--profile", url.path, "--yes"],
        success: "MCP approved. Restart the connector to apply changes.")
      await refresh()
    }
  }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
  var model: CompanionModel?
  var preferences: AppPreferences?
  func applicationDidFinishLaunching(_ notification: Notification) {
    NSApp.appearance = NSAppearance(named: .darkAqua)
    if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
      let image = NSImage(contentsOf: url)
    {
      NSApp.applicationIconImage = image
    }
  }
  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
  func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool
  {
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
      CompanionOverview(model: model, preferences: preferences)
        .onAppear {
          delegate.model = model
          delegate.preferences = preferences
          model.startMonitoring()
        }
    }
    .windowResizability(.contentSize)
    Settings { SettingsScreen(model: model, preferences: preferences) }
    MenuBarExtra(
      "OpenMaskit Companion", systemImage: "link",
      isInserted: Binding(
        get: { preferences.menuBarVisible },
        // Scene insertion echoes must not overwrite explicit user preferences.
        set: { preferences.synchronizeMenuBarInsertion($0) })
    ) {
      CompanionMenu(model: model, preferences: preferences)
    }.menuBarExtraStyle(.menu)
  }
}
