import AppKit
import CompanionDesktopCore
import CompanionPolicy
import SwiftUI

private struct SettingsHeight: PreferenceKey {
  static var defaultValue: CGFloat = 0
  static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
    value = max(value, nextValue())
  }
}

struct SettingsScreen: View {
  @ObservedObject var model: CompanionModel
  @ObservedObject var preferences: AppPreferences
  @Environment(\.openWindow) private var openWindow
  @State private var section = "installation"
  @State private var contentHeight: CGFloat = 400

  var body: some View {
    VStack(spacing: CompanionTokens.spaceMd) {
      Picker("Settings section", selection: $section) {
        Text("Installation").tag("installation")
        Text("Appearance").tag("appearance")
      }.pickerStyle(.segmented)
      ScrollView {
        VStack(spacing: CompanionTokens.spaceMd) {
          if section == "installation" {
            installationSettings
            InstallationFeedback(model: model)
          } else {
            appearanceSettings
          }
        }
        .frame(maxWidth: .infinity)
        .background(
          GeometryReader { geometry in
            Color.clear.preference(key: SettingsHeight.self, value: geometry.size.height)
          })
      }
      .frame(
        height: min(contentHeight, max(250, (NSScreen.main?.visibleFrame.height ?? 800) - 200))
      )
      .onPreferenceChange(SettingsHeight.self) { height in
        if height > 0 && abs(contentHeight - height) > 0.5 { contentHeight = height }
      }
    }
    .toggleStyle(.switch).controlSize(.small)
    .font(CompanionTypography.body).foregroundStyle(CompanionTheme.text)
    .tint(CompanionTheme.accent).padding(CompanionTokens.spaceLg)
    .frame(width: 620).fixedSize(horizontal: false, vertical: true)
    .background(CompanionTheme.root).preferredColorScheme(.dark)
    .onAppear { preferences.openMainWindow = { openWindow(id: "main") } }
  }

  @ViewBuilder private var installationSettings: some View {
    if model.installation.configured {
      CompanionPanel("Current installation", detail: model.installation.title) {
        Text(model.installation.dashboard ?? "").textSelection(.enabled)
        if model.installation.mode == .existing {
          Text(
            "Managed outside Companion. Its existing rules, settings and services remain in place."
          )
          .foregroundStyle(CompanionTheme.secondary).fixedSize(horizontal: false, vertical: true)
        }
        if let issue = model.installation.error ?? model.installation.connectionError {
          Text(issue).foregroundStyle(CompanionTheme.orange)
            .fixedSize(horizontal: false, vertical: true)
        }
        HStack {
          Button("Check Connection") { Task { await model.refresh() } }
            .buttonStyle(CompanionButtonStyle()).disabled(model.busy)
          Button("Open OpenMaskit") { Task { await model.openDashboard() } }
            .buttonStyle(CompanionButtonStyle()).disabled(
              !model.installation.canOpenDashboard || model.busy)
        }
      }
    }
    if model.installation.canManageServices {
      CompanionPanel("Services") {
        if model.installation.services.isEmpty {
          Text("Services are stopped.").foregroundStyle(CompanionTheme.secondary)
        }
        ForEach(model.installation.services) { service in
          HStack {
            Text(service.title)
            Spacer()
            Text(service.health.isEmpty ? service.state : service.health)
              .foregroundStyle(CompanionTheme.secondary)
          }
        }
        HStack {
          Button("Start Services") {
            Task { await model.action(["start"], success: "Services started.") }
          }
          .buttonStyle(CompanionButtonStyle(kind: .primary))
          .disabled(model.installation.ready || model.busy)
          Button("Stop Services") {
            Task {
              await model.action(["stop"], success: "Services stopped. Your settings are saved.")
            }
          }
          .buttonStyle(CompanionButtonStyle(kind: .danger))
          .disabled(
            model.busy || !model.installation.services.contains(where: { $0.state == "running" }))
        }
      }
    }
    InstallationSetup(model: model)
    if model.installation.mode == .managed && model.installation.configured {
      CompanionPanel("Local MCP connection") {
        Text(
          model.installation.paired
            ? "This Mac is paired." : "Pair this Mac to connect approved local MCPs."
        )
        .foregroundStyle(CompanionTheme.secondary)
        HStack {
          Button(model.installation.paired ? "Pair Again" : "Pair This Mac") {
            Task { await model.pair() }
          }
          .buttonStyle(CompanionButtonStyle()).disabled(
            model.busy || !model.installation.canUseLocalConnector)
          Button(model.connectorRunning ? "Stop Connector" : "Start Connector") {
            model.toggleConnector()
          }
          .buttonStyle(CompanionButtonStyle())
          .disabled(
            model.busy
              || (!model.connectorRunning
                && (!model.installation.canUseLocalConnector || !model.installation.paired))
          )
        }
      }
    }
  }

  private var appearanceSettings: some View {
    VStack(spacing: CompanionTokens.spaceMd) {
      CompanionPanel("Menu bar & window") {
        Toggle("Show OpenMaskit Companion in the menu bar", isOn: $preferences.showInMenuBar)
          .help("The connection icon appears in the macOS menu bar at the top of the screen.")
        Divider().overlay(CompanionTheme.border)
        Toggle(
          "Keep running in the menu bar when I close the window", isOn: $preferences.closeToMenuBar)
        Text(
          "When enabled, closing the window hides its Dock icon. Reopen or quit from the menu bar; services and MCP connections keep running."
        )
        .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
      }
      CompanionPanel("Startup & updates") {
        Text("Start the app manually. Updates are manual in this development build.")
          .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
      }
    }
  }
}

struct CompanionMenu: View {
  @ObservedObject var model: CompanionModel
  @ObservedObject var preferences: AppPreferences
  @Environment(\.openWindow) private var openWindow

  var body: some View {
    Button("Show OpenMaskit Companion") {
      preferences.revealMainWindow()
    }
    Button("Open OpenMaskit Dashboard") {
      Task { await model.openDashboard() }
    }.disabled(!model.installation.canOpenDashboard || model.busy)
    Divider()
    Text(
      model.installation.connectors?.contains(where: { $0.connected }) == true
        ? "Local connector connected" : "Local connector offline")
    Button(model.connectorRunning ? "Stop Local Connector" : "Start Local Connector") {
      model.toggleConnector()
    }.disabled(!model.installation.canUseLocalConnector || !model.installation.paired || model.busy)
    Divider()
    SettingsLink { Text("Settings…") }.keyboardShortcut(",")
    Button("Quit OpenMaskit Companion") { NSApp.terminate(nil) }.keyboardShortcut("q")
      .onAppear { preferences.openMainWindow = { openWindow(id: "main") } }
  }
}

struct MainWindowObserver: NSViewRepresentable {
  let preferences: AppPreferences
  @Environment(\.openWindow) private var openWindow

  func makeCoordinator() -> Coordinator { Coordinator(preferences) }
  func makeNSView(context: Context) -> NSView { NSView() }
  func updateNSView(_ view: NSView, context: Context) {
    let action = openWindow
    DispatchQueue.main.async {
      preferences.openMainWindow = { action(id: "main") }
      context.coordinator.observe(view.window)
    }
  }

  @MainActor final class Coordinator {
    let preferences: AppPreferences
    private var token: NSObjectProtocol?
    private weak var window: NSWindow?
    init(_ preferences: AppPreferences) { self.preferences = preferences }

    func observe(_ window: NSWindow?) {
      guard let window, self.window !== window else { return }
      if let token { NotificationCenter.default.removeObserver(token) }
      self.window = window
      window.titlebarAppearsTransparent = true
      window.backgroundColor = NSColor(CompanionTheme.root)
      token = NotificationCenter.default.addObserver(
        forName: NSWindow.willCloseNotification,
        object: window, queue: .main
      ) { [weak preferences] _ in
        MainActor.assumeIsolated { preferences?.windowClosed() }
      }
    }

    deinit {
      if let token { NotificationCenter.default.removeObserver(token) }
    }
  }
}
