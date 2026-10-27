import AppKit
import CompanionDesktopCore
import XCTest

@testable import OpenMaskitCompanion

@MainActor final class StatusItemTests: XCTestCase {
  func testOneNativeItemIsRetainedUntilExplicitStopAndCanRestart() throws {
    let f = try AppTestFixture()
    let suite = "companion-status-item-" + UUID().uuidString
    let defaults = UserDefaults(suiteName: suite)!
    defer {
      f.close()
      defaults.removePersistentDomain(forName: suite)
    }
    _ = NSApplication.shared
    let preferences = AppPreferences(
      defaults: defaults, setActivationPolicy: { _ in }, activate: {})
    let owner = CompanionStatusItem(model: f.model, preferences: preferences)
    defer { owner.stop() }
    XCTAssertNil(owner.statusItem)
    owner.start()
    let item = try XCTUnwrap(owner.statusItem)
    XCTAssertTrue(item.statusBar === NSStatusBar.system)
    XCTAssertTrue(item.menu === owner.menu)
    XCTAssertEqual(item.length, NSStatusItem.squareLength)
    XCTAssertEqual(item.behavior, [])
    XCTAssertTrue(item.isVisible)
    XCTAssertNotNil(item.button?.image)
    XCTAssertTrue(item.button?.image?.isTemplate == true)
    XCTAssertEqual(item.button?.accessibilityLabel(), "OpenMaskit Companion")
    XCTAssertFalse(owner.menu.items.isEmpty)
    owner.start()
    XCTAssertTrue(owner.statusItem === item, "Repeated startup must not create a second icon")
    preferences.windowPresented()
    preferences.windowClosed()
    XCTAssertTrue(owner.statusItem === item)
    XCTAssertTrue(item.isVisible)
    owner.stop()
    XCTAssertNil(owner.statusItem)
    owner.stop()
    owner.start()
    XCTAssertNotNil(owner.statusItem)
    XCTAssertFalse(owner.statusItem === item)
    XCTAssertTrue(f.actions.isEmpty)
  }
}
