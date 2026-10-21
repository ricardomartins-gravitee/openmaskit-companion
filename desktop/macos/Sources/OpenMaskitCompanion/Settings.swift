import AppKit
import CompanionDesktopCore
import CompanionPolicy
import SwiftUI

struct SettingsScreen: View {
  @ObservedObject var preferences: AppPreferences
  @Environment(\.openWindow) private var openWindow

  var body: some View {
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
        Text(
          "Start the app manually. Updates are manual in this development build."
        )
        .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
      }
    }
    .toggleStyle(.switch).controlSize(.small)
    .font(CompanionTypography.body).foregroundStyle(CompanionTheme.text)
    .tint(CompanionTheme.accent).padding(CompanionTokens.spaceLg)
    .frame(width: 520).fixedSize(horizontal: false, vertical: true)
    .background(CompanionTheme.root).preferredColorScheme(.dark)
    .onAppear {
      preferences.openMainWindow = { openWindow(id: "main") }
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
      NSWorkspace.shared.open(URL(string: "http://127.0.0.1:9493")!)
    }
    Divider()
    Text(
      model.installation.connectors?.contains(where: { $0.connected }) == true
        ? "Local connector connected" : "Local connector offline")
    Button(model.connectorRunning ? "Stop Local Connector" : "Start Local Connector") {
      model.toggleConnector()
    }.disabled(!model.installation.paired)
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
