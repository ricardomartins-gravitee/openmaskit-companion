import AppKit
import CompanionDesktopCore
import CompanionPolicy

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

/// App-owned status item, independent of SwiftUI window/scene disposal.
@MainActor final class CompanionStatusItem: NSObject, NSMenuDelegate {
  private let model: CompanionModel
  private let preferences: AppPreferences
  let menu = NSMenu(title: "OpenMaskit Companion")
  private(set) var statusItem: NSStatusItem?

  private enum Command: Int {
    case installation, setup, dashboard, startAll, stopAll, connector, localMCPs, settings, quit
  }

  init(model: CompanionModel, preferences: AppPreferences) {
    self.model = model
    self.preferences = preferences
    super.init()
    menu.autoenablesItems = false
    menu.delegate = self
  }

  func start() {
    guard statusItem == nil else { return }
    menuNeedsUpdate(menu)
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    item.autosaveName = "OpenMaskitCompanion.status"
    // Keep the app reachable until explicit Quit, including during window and
    // activation-policy changes. Do not opt into removal-triggered termination.
    item.behavior = []
    let image = NSImage(systemSymbolName: "link", accessibilityDescription: "OpenMaskit Companion")
    image?.isTemplate = true
    image?.size = NSSize(width: 18, height: 18)
    item.button?.image = image
    item.button?.toolTip = "OpenMaskit Companion"
    item.button?.setAccessibilityLabel("OpenMaskit Companion")
    item.menu = menu
    statusItem = item
  }

  func stop() {
    guard let item = statusItem else { return }
    NSStatusBar.system.removeStatusItem(item)
    statusItem = nil
  }

  func menuNeedsUpdate(_ menu: NSMenu) {
    guard menu === self.menu else { return }
    menu.removeAllItems()
    if model.menuStatus.offersDetails {
      add("OpenMaskit · " + model.menuStatus.rawValue + "…", command: .installation)
    } else {
      add("OpenMaskit · " + model.menuStatus.rawValue, enabled: false)
    }
    menu.addItem(.separator())
    if model.installation.configured {
      add(
        "Open Dashboard", command: .dashboard,
        enabled: model.installation.canOpenDashboard && !model.busy)
    } else if model.hasLoaded {
      add("Set Up OpenMaskit…", command: .setup)
    }
    if model.installation.canManageServices && model.installation.configured {
      let services = NSMenu(title: "Services")
      services.autoenablesItems = false
      let parent = add("Services")
      parent.submenu = services
      add(
        "Start All", command: .startAll, enabled: !model.busy && !model.runtimeIsReady, to: services
      )
      add(
        "Stop All", command: .stopAll,
        enabled: !model.busy
          && (model.connectorRunning
            || model.installation.services.contains { $0.state == "running" }),
        to: services)
      add(
        model.connectorRunning ? "Stop Local Connector" : "Start Local Connector",
        command: .connector,
        enabled: !model.busy
          && (model.connectorRunning
            || (model.installation.canUseLocalConnector && model.installation.paired)),
        to: services)
      services.addItem(.separator())
      add("Service Details…", command: .installation, to: services)
      add("Local MCP Settings…", command: .localMCPs, to: services)
    }
    menu.addItem(.separator())
    add("Settings…", command: .settings, key: ",")
    add("Quit OpenMaskit Companion", command: .quit, key: "q")
  }

  @discardableResult private func add(
    _ title: String, command: Command? = nil, key: String = "", enabled: Bool = true,
    to parent: NSMenu? = nil
  ) -> NSMenuItem {
    let item = NSMenuItem(
      title: title, action: command == nil ? nil : #selector(performCommand(_:)), keyEquivalent: key
    )
    item.target = self
    item.tag = command?.rawValue ?? -1
    item.isEnabled = enabled
    (parent ?? menu).addItem(item)
    return item
  }

  @objc private func performCommand(_ sender: NSMenuItem) {
    guard sender.isEnabled, let command = Command(rawValue: sender.tag) else { return }
    switch command {
    case .installation: showInstallation()
    case .setup: preferences.revealMainWindow()
    case .dashboard:
      guard !model.busy && model.installation.canOpenDashboard else { return }
      Task { await model.openDashboard() }
    case .startAll:
      guard !model.busy && model.installation.canManageServices else { return }
      Task { await model.startAll() }
    case .stopAll:
      guard !model.busy && model.installation.canManageServices else { return }
      Task { await model.stopAll() }
    case .connector:
      guard !model.busy && model.installation.canManageServices else { return }
      Task { await model.toggleConnector() }
    case .localMCPs:
      model.settingsSection = "mcps"
      model.showSettings?()
    case .settings: model.showSettings?()
    case .quit: NSApp.terminate(nil)
    }
  }

  private func showInstallation() {
    model.settingsSection = "installation"
    model.showSettings?()
  }
}
