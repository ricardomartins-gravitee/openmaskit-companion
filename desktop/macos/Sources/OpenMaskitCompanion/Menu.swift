import AppKit
import CompanionDesktopCore
import CompanionPolicy
import SwiftUI

enum CompanionMenuStatus: String {
  case checking = "Checking…"
  case working = "Working…"
  case setupRequired = "Setup required"
  case ready = "Ready"
  case stopped = "Stopped"
  case needsAttention = "Needs attention"
  case unavailable = "Unavailable"

  var offersDetails: Bool { self == .needsAttention || self == .unavailable }
}

extension CompanionModel {
  var menuStatus: CompanionMenuStatus {
    if busy { return .working }
    guard hasLoaded else { return message.isEmpty ? .checking : .needsAttention }
    guard installation.configured else { return .setupRequired }
    if installation.mode == .existing {
      guard installation.ready else { return .unavailable }
      return installation.health == "healthy" ? .ready : .needsAttention
    }
    if requirements?.ready == false || installation.error != nil
      || installation.connectionError != nil
    {
      return .needsAttention
    }
    if runtimeIsReady && installation.canOpenDashboard && installation.health == "healthy" {
      return .ready
    }
    return connectorRunning || installation.services.contains { $0.state == "running" }
      ? .needsAttention : .stopped
  }
}

struct CompanionMenu: View {
  @ObservedObject var model: CompanionModel
  @ObservedObject var preferences: AppPreferences

  var body: some View {
    if model.menuStatus.offersDetails {
      Button("OpenMaskit · " + model.menuStatus.rawValue + "…") { showInstallation() }
    } else {
      Text("OpenMaskit · " + model.menuStatus.rawValue)
    }
    Divider()
    if model.installation.configured {
      Button("Open Dashboard") { Task { await model.openDashboard() } }
        .disabled(!model.installation.canOpenDashboard || model.busy)
    } else if model.hasLoaded {
      Button("Set Up OpenMaskit…") { preferences.revealMainWindow() }
    }
    if model.installation.canManageServices && model.installation.configured {
      Menu("Services") { serviceControls }
    }
    Divider()
    Button("Settings…") { model.showSettings?() }.keyboardShortcut(",")
    Button("Quit OpenMaskit Companion") { NSApp.terminate(nil) }.keyboardShortcut("q")
  }

  private var serviceControls: some View {
    Group {
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
      Divider()
      Button("Service Details…") { showInstallation() }
      Button("Local MCP Settings…") {
        model.settingsSection = "mcps"
        model.showSettings?()
      }
    }
  }

  private func showInstallation() {
    model.settingsSection = "installation"
    model.showSettings?()
  }
}
