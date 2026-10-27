import AppKit
import CompanionDesktopCore
import Foundation
import XCTest

@testable import OpenMaskitCompanion

@MainActor final class AppLifecycleTests: XCTestCase {
  func withDelegate(
    _ f: AppTestFixture, operation: (AppDelegate, AppPreferences, () -> Int) async throws -> Void
  ) async throws {
    let app = NSApplication.shared
    let original = app.activationPolicy()
    let appearance = app.appearance
    let suite = "companion-coordinator-tests-" + UUID().uuidString
    let defaults = UserDefaults(suiteName: suite)!
    let preferences = AppPreferences(defaults: defaults, activate: {})
    var monitorStarts = 0
    let delegate = AppDelegate(
      model: f.model, preferences: preferences, beginMonitoring: { _, _ in monitorStarts += 1 })
    delegate.applicationDidFinishLaunching(
      Notification(name: NSApplication.didFinishLaunchingNotification))
    defer {
      for window in app.windows where window.windowController is CompanionWindow { window.close() }
      delegate.applicationWillTerminate(Notification(name: NSApplication.willTerminateNotification))
      app.setActivationPolicy(original)
      app.appearance = appearance
      defaults.removePersistentDomain(forName: suite)
    }
    try await operation(delegate, preferences, { monitorStarts })
  }

  func testConfiguredLaunchHasNoMainWindowAndReopeningReusesSettings() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    try await withDelegate(f) { delegate, preferences, starts in
      await f.model.refresh()
      XCTAssertEqual(starts(), 1)
      XCTAssertEqual(NSApp.activationPolicy(), .accessory)
      XCTAssertFalse(
        NSApp.windows.contains { $0.isVisible && $0.windowController is CompanionWindow })
      XCTAssertFalse(delegate.applicationShouldTerminateAfterLastWindowClosed(NSApp))
      XCTAssertFalse(delegate.applicationShouldHandleReopen(NSApp, hasVisibleWindows: false))
      let settings = try XCTUnwrap(
        NSApp.windows.first { $0.isVisible && $0.title == "OpenMaskit Companion Settings" })
      XCTAssertEqual(NSApp.activationPolicy(), .regular)
      f.model.showSettings?()
      XCTAssertEqual(NSApp.windows.filter { $0.isVisible && $0.title == settings.title }.count, 1)
      settings.close()
      XCTAssertEqual(NSApp.activationPolicy(), .accessory)
      XCTAssertTrue(preferences.menuBarVisible)
      XCTAssertEqual(starts(), 1, "Reopening Settings must not restart monitoring or services")
    }
  }

  func testFreshLaunchShowsOnboardingAndCompletingSetupReturnsToMenuBar() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    var fresh = AppTestFixture.state()
    fresh["mode"] = "unconfigured"
    fresh["configured"] = false
    fresh["ready"] = false
    f.replies["status"] = ["body": fresh]
    try f.save()
    try await withDelegate(f) { delegate, preferences, _ in
      await f.model.refresh()
      let onboarding = try XCTUnwrap(
        NSApp.windows.first { $0.isVisible && $0.title == "Set Up OpenMaskit Companion" })
      XCTAssertEqual(NSApp.activationPolicy(), .regular)
      XCTAssertFalse(delegate.applicationShouldHandleReopen(NSApp, hasVisibleWindows: true))
      XCTAssertEqual(NSApp.windows.filter { $0.isVisible && $0.title == onboarding.title }.count, 1)
      try f.loadManaged()
      XCTAssertFalse(onboarding.isVisible)
      XCTAssertEqual(NSApp.activationPolicy(), .accessory)
      XCTAssertTrue(preferences.menuBarVisible)
    }
  }

  func testQuitStopsTheAppOwnedConnector() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    try f.loadManaged(paired: true)
    try await withDelegate(f) { delegate, _, _ in
      await f.model.toggleConnector()
      XCTAssertTrue(f.model.connectorRunning)
      delegate.applicationWillTerminate(Notification(name: NSApplication.willTerminateNotification))
      XCTAssertFalse(f.model.connectorRunning)
      XCTAssertFalse(f.model.connectorIsOnline)
    }
  }
}
