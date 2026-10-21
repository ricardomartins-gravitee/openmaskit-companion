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

  func testCloseCallsAppKitAdapterAndReopenRestoresDockAndWindow() async {
    var policies: [NSApplication.ActivationPolicy] = []
    var opened = 0
    var activated = 0
    let preferences = AppPreferences(
      defaults: privateDefaults(),
      setActivationPolicy: { policies.append($0) }, activate: { activated += 1 })
    preferences.openMainWindow = { opened += 1 }
    preferences.closeToMenuBar = true
    preferences.windowClosed()
    XCTAssertEqual(policies, [.accessory])
    XCTAssertTrue(preferences.mainWindowClosed)
    XCTAssertTrue(preferences.menuBarVisible)
    XCTAssertEqual(opened, 0, "Closing must never reopen the window through scene appearance")
    XCTAssertFalse(preferences.showInMenuBar)
    preferences.revealMainWindow()
    XCTAssertEqual(policies, [.accessory, .regular])
    XCTAssertEqual(opened, 1)
    XCTAssertEqual(activated, 1)
    XCTAssertFalse(preferences.mainWindowClosed)
    XCTAssertFalse(preferences.menuBarVisible)
  }

  func testDefaultsAndIndependentPreferencePersistence() async {
    let defaults = privateDefaults()
    let preferences = AppPreferences(
      defaults: defaults, setActivationPolicy: { _ in }, activate: {})
    XCTAssertFalse(preferences.showInMenuBar)
    XCTAssertFalse(preferences.closeToMenuBar)
    preferences.closeToMenuBar = true
    preferences.windowClosed()
    XCTAssertFalse(defaults.bool(forKey: "showInMenuBar"))
    let relaunched = AppPreferences(defaults: defaults, setActivationPolicy: { _ in }, activate: {})
    XCTAssertTrue(relaunched.closeToMenuBar)
    XCTAssertFalse(relaunched.showInMenuBar)
    XCTAssertFalse(relaunched.mainWindowClosed, "A new launch starts with its window visible")
  }

  func testDisablingCloseWhileHiddenReopensWindow() async {
    var policies: [NSApplication.ActivationPolicy] = []
    var opened = 0
    let preferences = AppPreferences(
      defaults: privateDefaults(),
      setActivationPolicy: { policies.append($0) }, activate: {})
    preferences.openMainWindow = { opened += 1 }
    preferences.closeToMenuBar = true
    preferences.windowClosed()
    preferences.closeToMenuBar = false
    XCTAssertEqual(policies, [.accessory, .regular])
    XCTAssertEqual(opened, 1)
    XCTAssertFalse(preferences.mainWindowClosed)
  }

  func testIdenticalPreferencesDoNotPublishFeedback() async {
    let preferences = AppPreferences(
      defaults: privateDefaults(), setActivationPolicy: { _ in }, activate: {})
    var changes = 0
    let token = preferences.objectWillChange.sink { changes += 1 }
    preferences.showInMenuBar = false
    preferences.closeToMenuBar = false
    XCTAssertEqual(changes, 0)
    preferences.showInMenuBar = true
    XCTAssertEqual(changes, 1)
    preferences.showInMenuBar = true
    XCTAssertEqual(changes, 1)
    withExtendedLifetime(token) {}
  }

  func testFrameworkInsertionEchoDoesNotChangeIndependentPreferences() async {
    let defaults = privateDefaults()
    let preferences = AppPreferences(
      defaults: defaults, setActivationPolicy: { _ in }, activate: {})
    preferences.closeToMenuBar = true
    preferences.windowClosed()
    var changes = 0
    let observation = preferences.objectWillChange.sink { changes += 1 }
    for inserted in [true, false, true, false] {
      preferences.synchronizeMenuBarInsertion(inserted)
    }
    XCTAssertEqual(changes, 0)
    XCTAssertTrue(preferences.mainWindowClosed)
    XCTAssertFalse(preferences.showInMenuBar)
    XCTAssertFalse(defaults.bool(forKey: "showInMenuBar"))
    withExtendedLifetime(observation) {}
  }

  func testActualAppKitActivationPolicies() async {
    let application = NSApplication.shared
    let original = application.activationPolicy()
    defer { application.setActivationPolicy(original) }
    let preferences = AppPreferences(defaults: privateDefaults(), activate: {})
    preferences.closeToMenuBar = true
    preferences.windowClosed()
    XCTAssertEqual(application.activationPolicy(), .accessory)
    preferences.revealMainWindow()
    XCTAssertEqual(application.activationPolicy(), .regular)
  }
}
