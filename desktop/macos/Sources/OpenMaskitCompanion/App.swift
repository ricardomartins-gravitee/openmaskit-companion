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
  @Published var installation = Installation() {
    didSet { if hasLoaded { configurationChanged?() } }
  }
  var didLoad: (() -> Void)?
  var configurationChanged: (() -> Void)?
  var showSettings: (() -> Void)?
  @Published var settingsSection = "installation"
  var connectorIsOnline: Bool { connectorRunning && connectorWasOnline }
  var runtimeIsReady: Bool {
    installation.servicesAreHealthy
      && (!installation.paired || profiles.isEmpty || connectorIsOnline)
  }
  @Published var profiles: [LocalProfile] = []
  @Published var busy = false
  @Published var hasLoaded = false
  @Published var progress = ""
  private var refreshing = false
  private var configurationGeneration = 0
  @Published var message = ""
  @Published var connectorRunning = false
  private var connector: Process?
  private var retiringConnector: Process?
  private var connectorWasOnline = false
  private var lastKeepAlive = ContinuousClock.now
  private let startup = ServiceStartup()
  private var monitor: Task<Void, Never>?

  func startMonitoring(preferences: AppPreferences) {
    guard monitor == nil else { return }
    monitor = Task { [weak self] in
      while !Task.isCancelled {
        await self?.refresh()
        if let self, self.hasLoaded && !self.startup.launchAttempted {
          await self.startAll(automatically: true, enabled: preferences.automaticallyStartServices)
        }
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
    let longActions = ["start", "prepare-managed"]
    let runtimeActions = [
      "start-dependencies", "start-installed", "wait-services", "refresh-connections",
      "keep-connections", "register",
    ]
    let timeout: TimeInterval =
      longActions.contains(arguments.first ?? "")
      ? 420
      : (runtimeActions.contains(arguments.first ?? "") ? 200 : 45)
    let result = try await BackendProcess.run(
      executable: executable, arguments: allArguments, input: input, timeout: timeout)
    guard result.status == 0 else {
      let failure = try? JSONSerialization.jsonObject(with: result.errors) as? [String: String]
      let safeCodes = [
        "invalid_url", "unavailable", "not_openmaskit", "database_unavailable",
        "invalid_selection", "external_installation", "not_configured", "docker_unavailable",
      ]
      let detail = failure.flatMap { safeCodes.contains($0["code"] ?? "") ? $0["error"] : nil }
      throw NSError(
        domain: "Companion", code: 1,
        userInfo: [
          NSLocalizedDescriptionKey:
            detail
            ?? "The action could not finish. Check Docker Desktop, pairing and your local MCP settings."
        ])
    }
    return result.output
  }

  func refresh() async {
    guard !busy && !refreshing else { return }
    refreshing = true
    defer { refreshing = false }
    let generation = configurationGeneration
    do {
      let state = try JSONDecoder().decode(Installation.self, from: await invoke(["status"]))
      struct ProfileList: Codable { let profiles: [LocalProfile] }
      let list =
        state.mode == .managed
        ? try JSONDecoder().decode(ProfileList.self, from: await invoke(["profiles"]))
        : ProfileList(profiles: [])
      guard generation == configurationGeneration && !busy else { return }
      installation = state
      profiles = list.profiles
      let firstLoad = !hasLoaded
      hasLoaded = true
      if firstLoad { didLoad?() }
      if connectorRunning {
        let online = (try? await connectorOnline()) ?? false
        if online && !connectorWasOnline {
          busy = true
          defer { busy = false }
          try await restoreConnections()
        }
        connectorWasOnline = online
        if online && ContinuousClock.now - lastKeepAlive >= .seconds(60) {
          lastKeepAlive = .now
          busy = true
          defer { busy = false }
          do {
            struct Kept: Decodable { let failed: Int }
            let result = try JSONDecoder().decode(
              Kept.self, from: await invoke(["keep-connections"]))
            if result.failed > 0 {
              message = "A local MCP is not responding. Restart its connector in Settings."
            }
          } catch {
            message = "Local MCP connection check failed. Check its status in Settings."
          }
        }
      }
    } catch {
      guard generation == configurationGeneration && !busy else { return }
      installation.ready = false
      message = error.localizedDescription
    }
  }

  private func connectorOnline() async throws -> Bool {
    struct Status: Decodable { let connected: Bool }
    return try JSONDecoder().decode(Status.self, from: await invoke(["connector-status"])).connected
  }

  private func restoreConnections(waitReady: Bool = false) async throws {
    struct Status: Decodable { let connected: Bool }
    let args = ["refresh-connections"] + (waitReady ? ["--wait-ready"] : [])
    let result = try JSONDecoder().decode(Status.self, from: await invoke(args))
    guard result.connected else { throw StartupFailure.connectorUnavailable }
    lastKeepAlive = .now
  }

  private var startupActions: StartupActions {
    StartupActions(
      dockerReady: {
        struct Status: Decodable { let ready: Bool }
        return try JSONDecoder().decode(Status.self, from: await self.invoke(["docker-status"]))
          .ready
      },
      openDocker: {
        guard
          let application = NSWorkspace.shared.urlForApplication(
            withBundleIdentifier: "com.docker.docker")
        else { throw StartupFailure.dockerUnavailable }
        let config = NSWorkspace.OpenConfiguration()
        config.activates = false
        try await withCheckedThrowingContinuation {
          (continuation: CheckedContinuation<Void, Error>) in
          NSWorkspace.shared.openApplication(at: application, configuration: config) { _, error in
            if let error { continuation.resume(throwing: error) } else { continuation.resume() }
          }
        }
      },
      startDependencies: { _ = try await self.invoke(["start-dependencies"]) },
      startConnector: { try await self.startConnectorProcess() },
      connectorReady: { try await self.connectorOnline() },
      startOpenMaskit: { _ = try await self.invoke(["start-installed"]) },
      refreshConnections: { try await self.restoreConnections(waitReady: true) },
      waitForServices: {
        try JSONDecoder().decode(Installation.self, from: await self.invoke(["wait-services"]))
      },
      progress: { self.progress = $0 })
  }

  func startAll(automatically: Bool = false, enabled: Bool = true) async {
    guard !busy else { return }
    if !automatically && (!installation.configured || installation.mode != .managed) { return }
    busy = true
    configurationGeneration += 1
    message = ""
    defer {
      busy = false
      progress = ""
    }
    do {
      let result: Installation?
      if automatically {
        result = try await startup.onLaunch(
          state: installation, enabled: enabled, approvedProfiles: profiles.count,
          actions: startupActions)
      } else {
        result = try await ServiceStartup.start(
          state: installation, approvedProfiles: profiles.count, actions: startupActions)
      }
      if let result {
        installation = result
        let online = (try? await connectorOnline()) ?? false
        connectorWasOnline = connectorRunning && online
        message =
          connectorWasOnline ? "Services and the connector are ready." : "Services are ready."
      }
    } catch { message = error.localizedDescription }
  }

  func stopAll() async {
    guard !busy else { return }
    stopConnector()
    await action(["stop"], success: "Services stopped. Your rules and settings are saved.")
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

  func toggleConnector() async {
    guard !busy else { return }
    if connectorRunning {
      stopConnector()
      message = "Local connector stopped. It stays stopped until you start it or reopen Companion."
      return
    }
    guard installation.canUseLocalConnector && installation.paired else { return }
    busy = true
    progress = "Connecting local MCPs…"
    defer {
      busy = false
      progress = ""
    }
    do {
      try await startConnectorProcess()
      var ready = false
      for _ in 0..<15 {
        if try await connectorOnline() {
          ready = true
          break
        }
        try await Task.sleep(for: .seconds(2))
      }
      guard ready else { throw StartupFailure.connectorUnavailable }
      try await restoreConnections()
      connectorWasOnline = true
      message = "Local MCPs are connected."
    } catch { message = error.localizedDescription }
  }

  private func startConnectorProcess() async throws {
    if connectorRunning { return }
    if let old = retiringConnector {
      for _ in 0..<50 {
        if !old.isRunning { break }
        try await Task.sleep(for: .milliseconds(100))
      }
      guard !old.isRunning else { throw StartupFailure.connectorUnavailable }
      retiringConnector = nil
    }
    let process = Process()
    process.executableURL = backend
    process.arguments = baseArguments + ["connect"]
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    process.terminationHandler = { [weak self] terminated in
      Task { @MainActor in
        guard let self, self.connector === terminated else { return }
        self.connector = nil
        self.connectorRunning = false
        self.connectorWasOnline = false
      }
    }
    try process.run()
    connector = process
    connectorRunning = true
    connectorWasOnline = false
  }

  func stopConnector() {
    connector?.terminate()
    retiringConnector = connector
    connector = nil
    connectorRunning = false
    connectorWasOnline = false
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

@MainActor final class AppDelegate: NSObject, NSApplicationDelegate {
  let model = CompanionRuntime.model
  let preferences = CompanionRuntime.preferences
  private var onboarding: CompanionWindow?
  private var settings: CompanionWindow?

  func applicationDidFinishLaunching(_ notification: Notification) {
    DistributedNotificationCenter.default().addObserver(
      self, selector: #selector(reopenRunningApp(_:)),
      name: CompanionInstance.reopenNotification,
      object: String(ProcessInfo.processInfo.processIdentifier))
    NSApp.appearance = NSAppearance(named: .darkAqua)
    if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
      let image = NSImage(contentsOf: url)
    {
      NSApp.applicationIconImage = image
    }
    preferences.openMainWindow = { [weak self] in self?.reopen() }
    model.showSettings = { [weak self] in self?.showSettings() }
    model.didLoad = { [weak self] in
      guard let self else { return }
      if self.model.installation.configured {
        self.preferences.enterMenuBar()
      } else {
        self.showOnboarding()
      }
    }
    model.configurationChanged = { [weak self] in
      guard let self, self.model.installation.configured,
        self.onboarding?.window?.isVisible == true
      else { return }
      self.onboarding?.close()
      self.preferences.enterMenuBar()
    }
    model.startMonitoring(preferences: preferences)
  }
  func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
  func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool
  {
    preferences.revealMainWindow()
    return false
  }
  func applicationWillTerminate(_ notification: Notification) {
    DistributedNotificationCenter.default().removeObserver(self)
    MainActor.assumeIsolated { model.stopConnector() }
  }

  @objc private func reopenRunningApp(_ notification: Notification) {
    preferences.revealMainWindow()
  }

  private func reopen() {
    if model.hasLoaded && model.installation.needsOnboarding {
      showOnboarding()
    } else {
      showSettings()
    }
  }

  private func showOnboarding() {
    if onboarding == nil {
      onboarding = CompanionWindow(
        title: "Set Up OpenMaskit Companion",
        content: AnyView(CompanionOnboarding(model: model, preferences: preferences)),
        preferences: preferences)
    }
    onboarding?.present()
  }

  private func showSettings() {
    if settings == nil {
      settings = CompanionWindow(
        title: "OpenMaskit Companion Settings",
        content: AnyView(SettingsScreen(model: model, preferences: preferences)),
        preferences: preferences)
    }
    settings?.present()
  }
}

@main struct CompanionApp: App {
  @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
  @StateObject var model = CompanionRuntime.model
  @StateObject var preferences = CompanionRuntime.preferences

  init() { CompanionInstance.enforce() }

  var body: some Scene {
    MenuBarExtra("OpenMaskit Companion", systemImage: "link") {
      CompanionMenu(model: model, preferences: preferences)
    }.menuBarExtraStyle(.menu)
      .commands {
        CommandGroup(replacing: .appSettings) {
          Button("Settings…") { model.showSettings?() }.keyboardShortcut(",")
        }
      }
  }
}
