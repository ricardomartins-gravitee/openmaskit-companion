import AppKit
import CompanionDesktopCore
import SwiftUI
import XCTest

@testable import OpenMaskitCompanion

@available(macOS 14.4, *)
@MainActor private final class TestMenu {
  let menu: NSHostingMenu<CompanionMenu>
  let preferences: AppPreferences
  let defaults: UserDefaults
  let suite = "companion-menu-" + UUID().uuidString

  init(model: CompanionModel) {
    _ = NSApplication.shared
    defaults = UserDefaults(suiteName: suite)!
    preferences = AppPreferences(defaults: defaults, setActivationPolicy: { _ in }, activate: {})
    menu = NSHostingMenu(rootView: CompanionMenu(model: model, preferences: preferences))
  }

  func item(_ title: String, in parent: NSMenu? = nil) throws -> NSMenuItem {
    let parent = parent ?? menu
    parent.update()
    return try XCTUnwrap(parent.items.first { $0.title == title }, "Missing menu item: " + title)
  }

  func press(_ title: String, in parent: NSMenu? = nil) throws {
    let parent = parent ?? menu
    let selected = try item(title, in: parent)
    XCTAssertTrue(selected.isEnabled)
    parent.performActionForItem(at: parent.index(of: selected))
  }

  func close() { defaults.removePersistentDomain(forName: suite) }
}

@MainActor final class MenuInteractionTests: XCTestCase {
  func testManagedMenuKeepsServiceActionsInASubmenuAndDisablesBusyActions() async throws {
    guard #available(macOS 14.4, *) else {
      return XCTFail("The native menu test host requires macOS 14.4 or later")
    }
    let f = try AppTestFixture()
    try f.loadManaged()
    let host = TestMenu(model: f.model)
    defer {
      host.close()
      f.close()
    }
    try await f.waitFor {
      host.menu.update()
      return host.menu.items.contains { $0.title == "Settings…" }
    }
    XCTAssertEqual(
      host.menu.items.filter { !$0.isSeparatorItem }.map(\.title),
      [
        "OpenMaskit · Ready", "Open Dashboard", "Services", "Settings…",
        "Quit OpenMaskit Companion",
      ])
    let services = try XCTUnwrap(host.item("Services").submenu)
    services.update()
    XCTAssertEqual(
      services.items.filter { !$0.isSeparatorItem }.map(\.title),
      [
        "Start All", "Stop All", "Start Local Connector", "Service Details…", "Local MCP Settings…",
      ])
    XCTAssertFalse(try host.item("Start All", in: services).isEnabled)
    XCTAssertTrue(try host.item("Stop All", in: services).isEnabled)
    XCTAssertFalse(try host.item("Start Local Connector", in: services).isEnabled)
    XCTAssertEqual(try host.item("Settings…").keyEquivalent, ",")
    XCTAssertEqual(try host.item("Quit OpenMaskit Companion").keyEquivalent, "q")
    f.model.busy = true
    f.model.progress = String(repeating: "Synthetic long progress ", count: 50)
    try await f.waitFor {
      host.menu.update()
      return host.menu.items.contains { $0.title == "OpenMaskit · Working…" }
    }
    XCTAssertFalse(try host.item("Open Dashboard").isEnabled)
    let busyServices = try XCTUnwrap(host.item("Services").submenu)
    XCTAssertFalse(try host.item("Stop All", in: busyServices).isEnabled)
    XCTAssertTrue(try host.item("Settings…").isEnabled)
    XCTAssertTrue(f.actions.isEmpty)
  }

  func testNativeMenuRoutesSettingsAndSubmenuItemsToTheCorrectSection() async throws {
    guard #available(macOS 14.4, *) else {
      return XCTFail("The native menu test host requires macOS 14.4 or later")
    }
    let f = try AppTestFixture()
    try f.loadManaged()
    var opened = 0
    f.model.showSettings = { opened += 1 }
    let host = TestMenu(model: f.model)
    defer {
      host.close()
      f.close()
    }
    try await f.waitFor {
      host.menu.update()
      return host.menu.items.contains { $0.title == "Services" }
    }
    let services = try XCTUnwrap(host.item("Services").submenu)
    try host.press("Local MCP Settings…", in: services)
    try await f.waitFor { opened == 1 }
    XCTAssertEqual(f.model.settingsSection, "mcps")
    try host.press("Service Details…", in: services)
    try await f.waitFor { opened == 2 }
    XCTAssertEqual(f.model.settingsSection, "installation")
    try host.press("Settings…")
    try await f.waitFor { opened == 3 }
    XCTAssertTrue(f.actions.isEmpty)
  }

  func testExternalMenuOmitsServiceAdministrationAndVerifiesDashboardBeforeOpening() async throws {
    guard #available(macOS 14.4, *) else {
      return XCTFail("The native menu test host requires macOS 14.4 or later")
    }
    let f = try AppTestFixture()
    await f.model.refresh()
    f.replies["dashboard"] = ["body": ["ready": true, "dashboard": "http://127.0.0.1:19473"]]
    try f.save()
    let host = TestMenu(model: f.model)
    defer {
      host.close()
      f.close()
    }
    try await f.waitFor {
      host.menu.update()
      return host.menu.items.contains { $0.title == "Open Dashboard" }
    }
    XCTAssertFalse(host.menu.items.contains { $0.title == "Services" })
    try host.press("Open Dashboard")
    try await f.waitFor { !f.opened.isEmpty }
    XCTAssertEqual(f.opened.map(\.absoluteString), ["http://127.0.0.1:19473"])
    XCTAssertEqual(f.actions, ["status", "dashboard"])
  }
}
