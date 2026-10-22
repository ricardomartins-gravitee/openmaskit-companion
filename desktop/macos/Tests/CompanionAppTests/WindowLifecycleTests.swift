import AppKit
import CompanionDesktopCore
import SwiftUI
import XCTest

@testable import OpenMaskitCompanion

@MainActor final class WindowLifecycleTests: XCTestCase {
  func testClosingTheActualSettingsControllerHidesDockAndKeepsMenuPolicy() {
    let app = NSApplication.shared
    let original = app.activationPolicy()
    defer { app.setActivationPolicy(original) }
    let suite = "companion-window-tests-" + UUID().uuidString
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let preferences = AppPreferences(defaults: defaults, activate: {})
    let controller = CompanionWindow(
      title: "Synthetic Settings", content: AnyView(Text("Synthetic settings")),
      preferences: preferences)
    controller.present()
    XCTAssertTrue(controller.window?.isVisible == true)
    XCTAssertEqual(app.activationPolicy(), .regular)
    controller.close()
    XCTAssertFalse(controller.window?.isVisible == true)
    XCTAssertEqual(app.activationPolicy(), .accessory)
    XCTAssertTrue(preferences.menuBarVisible)
    XCTAssertTrue(preferences.mainWindowClosed)
    controller.present()
    XCTAssertEqual(app.activationPolicy(), .regular)
    controller.close()
    XCTAssertEqual(app.activationPolicy(), .accessory)
  }

  func testDockIsHiddenOnlyAfterTheLastCompanionWindowCloses() {
    let app = NSApplication.shared
    let original = app.activationPolicy()
    defer { app.setActivationPolicy(original) }
    let suite = "companion-window-tests-" + UUID().uuidString
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let preferences = AppPreferences(defaults: defaults, activate: {})
    let first = CompanionWindow(
      title: "Synthetic onboarding", content: AnyView(Text("Synthetic onboarding")),
      preferences: preferences)
    let second = CompanionWindow(
      title: "Synthetic Settings", content: AnyView(Text("Synthetic settings")),
      preferences: preferences)
    first.present()
    second.present()
    first.close()
    XCTAssertEqual(app.activationPolicy(), .regular)
    XCTAssertFalse(preferences.mainWindowClosed)
    second.close()
    XCTAssertEqual(app.activationPolicy(), .accessory)
    XCTAssertTrue(preferences.menuBarVisible)
  }
}
