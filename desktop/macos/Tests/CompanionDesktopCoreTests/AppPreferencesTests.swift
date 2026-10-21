import AppKit
import Combine
import XCTest

@testable import CompanionDesktopCore

@MainActor final class AppPreferencesTests: XCTestCase {
  func privateDefaults() -> UserDefaults {
    let name = "companion-tests-" + UUID().uuidString
    let defaults = UserDefaults(suiteName: name)!
    addTeardownBlock { defaults.removePersistentDomain(forName: name) }
    return defaults
  }

  func testRetiredVisibilityPreferencesCannotHideMenuOrReopenSettings() {
    let defaults = privateDefaults()
    for show in [false, true] {
      for close in [false, true] {
        defaults.set(show, forKey: "showInMenuBar")
        defaults.set(close, forKey: "closeToMenuBar")
        var policies: [NSApplication.ActivationPolicy] = []
        var opened = 0
        let preferences = AppPreferences(
          defaults: defaults,
          setActivationPolicy: { policies.append($0) }, activate: {})
        preferences.openMainWindow = { opened += 1 }
        preferences.enterMenuBar()
        XCTAssertTrue(preferences.menuBarVisible)
        XCTAssertEqual(policies.last, .accessory)
        XCTAssertEqual(opened, 0)
      }
    }
  }

  func testAutomaticStartupDefaultsOnAndPersistsOptOut() {
    let defaults = privateDefaults()
    let preferences = AppPreferences(
      defaults: defaults, setActivationPolicy: { _ in }, activate: {})
    XCTAssertTrue(preferences.automaticallyStartServices)
    preferences.automaticallyStartServices = false
    XCTAssertFalse(
      AppPreferences(defaults: defaults, setActivationPolicy: { _ in }, activate: {})
        .automaticallyStartServices)
  }

  func testCloseHidesDockWithoutReopeningAndReopenRestoresWindow() {
    var policies: [NSApplication.ActivationPolicy] = []
    var opened = 0
    var activated = 0
    var changes = 0
    let preferences = AppPreferences(
      defaults: privateDefaults(),
      setActivationPolicy: { policies.append($0) }, activate: { activated += 1 })
    preferences.openMainWindow = { opened += 1 }
    let observer = preferences.objectWillChange.sink { changes += 1 }
    preferences.windowClosed()
    XCTAssertEqual(policies, [.accessory])
    XCTAssertEqual(opened, 0)
    XCTAssertTrue(preferences.menuBarVisible && preferences.mainWindowClosed)
    let previous = changes
    preferences.windowClosed()
    XCTAssertEqual(changes, previous)
    XCTAssertEqual(policies, [.accessory])
    preferences.revealMainWindow()
    XCTAssertEqual(policies, [.accessory, .regular])
    XCTAssertEqual(opened, 1)
    XCTAssertEqual(activated, 1)
    XCTAssertFalse(preferences.mainWindowClosed)
    XCTAssertTrue(preferences.menuBarVisible)
    withExtendedLifetime(observer) {}
  }

  func testPresentingWindowDoesNotCreateReopenLoop() {
    var opened = 0
    let preferences = AppPreferences(
      defaults: privateDefaults(), setActivationPolicy: { _ in }, activate: {})
    preferences.openMainWindow = { opened += 1 }
    preferences.enterMenuBar()
    preferences.windowPresented()
    preferences.windowPresented()
    XCTAssertEqual(opened, 0)
    XCTAssertFalse(preferences.mainWindowClosed)
    XCTAssertTrue(preferences.menuBarVisible)
  }

  func testActualAppKitActivationPolicies() {
    let application = NSApplication.shared
    let original = application.activationPolicy()
    defer { application.setActivationPolicy(original) }
    let preferences = AppPreferences(defaults: privateDefaults(), activate: {})
    preferences.windowClosed()
    XCTAssertEqual(application.activationPolicy(), .accessory)
    preferences.revealMainWindow()
    XCTAssertEqual(application.activationPolicy(), .regular)
    XCTAssertTrue(preferences.menuBarVisible)
  }
}
