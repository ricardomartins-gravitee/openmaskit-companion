import AppKit
import CompanionPolicy
import CompanionDesktopCore
import SwiftUI

struct SettingsScreen: View {
    @ObservedObject var preferences: AppPreferences
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Form {
            Section("Menu bar and window") {
                Toggle("Show OpenMaskit Companion in the menu bar", isOn: $preferences.showInMenuBar)
                Toggle("Keep running in the menu bar when I close the window", isOn: $preferences.closeToMenuBar)
                Text("Closing the main window will hide the Dock icon. Use the menu bar icon to reopen the window or quit. Your services and local MCP connections keep running.")
                    .font(.callout).foregroundStyle(.secondary)
            }
            Section("Startup and updates") {
                Text("The app starts manually. Automatic updates are not enabled in this development build.")
                    .foregroundStyle(.secondary)
            }
        }
        .formStyle(.grouped).padding(10).frame(width: 540, height: 310)
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
        Text(model.installation.connectors?.contains(where: { $0.connected }) == true
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
            token = NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification,
                object: window, queue: .main) { [weak preferences] _ in
                    MainActor.assumeIsolated { preferences?.windowClosed() }
                }
        }

        deinit {
            if let token { NotificationCenter.default.removeObserver(token) }
        }
    }
}
