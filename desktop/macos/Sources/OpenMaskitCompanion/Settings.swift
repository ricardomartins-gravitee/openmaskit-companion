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
  @State private var contentHeight: CGFloat = 400

  var body: some View {
    VStack(spacing: CompanionTokens.spaceMd) {
      Picker("Settings section", selection: $model.settingsSection) {
        Text("Installation").tag("installation")
        Text("Local MCPs").tag("mcps")
        Text("General").tag("general")
      }.pickerStyle(.segmented)
      ScrollView {
        VStack(spacing: CompanionTokens.spaceMd) {
          if model.settingsSection == "installation" {
            installationSettings
            InstallationFeedback(model: model)
          } else if model.settingsSection == "mcps" {
            LocalMCPSettings(model: model)
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
          Button("Start All") {
            Task { await model.startAll() }
          }
          .buttonStyle(CompanionButtonStyle(kind: .primary))
          .disabled(
            !model.installation.configured || model.busy
              || model.runtimeIsReady)
          Button("Stop All") {
            Task { await model.stopAll() }
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
            Task { await model.toggleConnector() }
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
        Toggle(
          "Start services and local MCPs when Companion opens",
          isOn: $preferences.automaticallyStartServices)
        Text(
          "Opens Docker Desktop if needed and starts your configured installation and approved local MCPs. A manual stop lasts until the next launch."
        )
        .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
        Text("Login startup is off. Installation and updates remain manual.")
          .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
      }
    }
  }
}

struct CompanionMenu: View {
  @ObservedObject var model: CompanionModel
  @ObservedObject var preferences: AppPreferences

  var body: some View {
    Text(
      model.busy
        ? (model.progress.isEmpty ? "Working…" : model.progress)
        : "OpenMaskit · " + model.installation.title)
    if model.installation.configured {
      ForEach(model.installation.services) { service in
        Text(service.title + " · " + (service.health.isEmpty ? service.state : service.health))
      }
      if model.installation.mode == .managed {
        Text(model.connectorIsOnline ? "Local MCPs · Connected" : "Local MCPs · Offline")
      }
    } else {
      Text("Setup is required")
      Button("Set Up OpenMaskit…") { preferences.revealMainWindow() }
    }
    if !model.message.isEmpty { Text(model.message) }
    Divider()
    Button("Open OpenMaskit Dashboard") { Task { await model.openDashboard() } }
      .disabled(!model.installation.canOpenDashboard || model.busy)
    if model.installation.canManageServices && model.installation.configured {
      Button("Start All") { Task { await model.startAll() } }
        .disabled(model.busy || model.runtimeIsReady)
      Button("Stop All") { Task { await model.stopAll() } }
        .disabled(
          model.busy
            || (!model.connectorRunning
              && !model.installation.services.contains(where: { $0.state == "running" }))
        )
      Button(model.connectorRunning ? "Stop Local Connector" : "Start Local Connector") {
        Task { await model.toggleConnector() }
      }.disabled(
        model.busy
          || (!model.connectorRunning
            && (!model.installation.canUseLocalConnector || !model.installation.paired))
      )
    }
    Button("Refresh Status") { Task { await model.refresh() } }.disabled(model.busy)
    Divider()
    Button("Local MCP Settings…") {
      model.settingsSection = "mcps"
      model.showSettings?()
    }
    Button("Settings…") { model.showSettings?() }.keyboardShortcut(",")
    Button("Quit OpenMaskit Companion") { NSApp.terminate(nil) }.keyboardShortcut("q")
  }
}
