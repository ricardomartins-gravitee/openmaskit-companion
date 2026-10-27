import AppKit
import CompanionDesktopCore
import Foundation
import SwiftUI
import XCTest

@testable import OpenMaskitCompanion

/// The actual production components, hosted without the OS-owned scroll container.
private struct SettingsComponentHost: View {
  @ObservedObject var model: CompanionModel
  @ObservedObject var preferences: AppPreferences
  var body: some View {
    VStack(spacing: CompanionTokens.spaceMd) {
      SettingsSectionPicker(model: model)
      SettingsContents(model: model, preferences: preferences)
    }
    .toggleStyle(.switch).controlSize(.small)
    .font(CompanionTypography.body).foregroundStyle(CompanionTheme.text)
    .tint(CompanionTheme.accent).padding(CompanionTokens.spaceLg)
    .frame(width: 620).fixedSize(horizontal: false, vertical: true)
    .background(CompanionTheme.root).preferredColorScheme(.dark)
  }
}

/// In-process native UI testing: operates only on synthetic windows owned by this test process.
@MainActor private final class TestScreen {
  let controller: CompanionWindow
  let preferences: AppPreferences
  let defaults: UserDefaults
  let suite = "companion-screen-" + UUID().uuidString
  let originalPolicy = NSApplication.shared.activationPolicy()

  init(model: CompanionModel, onboarding: Bool = false, fullSettings: Bool = false) {
    defaults = UserDefaults(suiteName: suite)!
    preferences = AppPreferences(defaults: defaults, activate: {})
    let content: AnyView
    if onboarding {
      content = AnyView(CompanionOnboarding(model: model, preferences: preferences))
    } else if fullSettings {
      content = AnyView(SettingsScreen(model: model, preferences: preferences))
    } else {
      content = AnyView(SettingsComponentHost(model: model, preferences: preferences))
    }
    controller = CompanionWindow(
      title: "Synthetic Companion",
      // A swift-test host has no external assistive client. Ask SwiftUI to build
      // its accessibility tree in this synthetic window using its public environment.
      content: AnyView(content.environment(\.accessibilityEnabled, true)),
      preferences: preferences)
    if !NSApplication.shared.isRunning { NSApplication.shared.finishLaunching() }
    controller.present()
    controller.window?.contentView?.layoutSubtreeIfNeeded()
    controller.window?.displayIfNeeded()
  }

  func elements() -> [ScreenAccessibility] {
    controller.window?.contentView?.layoutSubtreeIfNeeded()
    var seen = Set<ObjectIdentifier>()
    var output: [ScreenAccessibility] = []
    func visit(_ value: Any) {
      guard output.count < 1_000, let object = value as? NSObject else {
        return
      }
      guard seen.insert(ObjectIdentifier(object)).inserted else { return }
      let element = ScreenAccessibility(object: object)
      output.append(element)
      for child in element.accessibilityChildren() ?? [] { visit(child) }
      if let view = object as? NSView {
        for child in view.subviews { visit(child) }
      }
    }
    if let window = controller.window { visit(window) }
    return output
  }

  func text(_ element: ScreenAccessibility) -> String {
    [
      element.accessibilityLabel(), element.accessibilityTitle(),
      element.accessibilityValue() as? String,
    ]
    .compactMap { $0 }.joined(separator: " ")
  }

  var allText: String { elements().map(text).joined(separator: "\n") }

  func element(id: String) throws -> ScreenAccessibility {
    try XCTUnwrap(
      elements().first { $0.accessibilityIdentifier() == id },
      "Missing native accessibility identifier: " + id)
  }

  func element(named name: String, role: NSAccessibility.Role? = nil) throws
    -> ScreenAccessibility
  {
    try XCTUnwrap(
      elements().first {
        (role == nil || $0.accessibilityRole() == role)
          && [$0.accessibilityLabel(), $0.accessibilityTitle(), $0.accessibilityValue() as? String]
            .contains(name)
      }, "Missing native control: " + name)
  }

  func press(_ element: ScreenAccessibility) {
    XCTAssertTrue(element.isAccessibilityEnabled())
    XCTAssertTrue(element.supportsPress, "The native control does not expose a press action")
    // Segmented controls can report false after changing selection. Each caller
    // waits for and verifies the actual binding/backend effect of the action.
    _ = element.accessibilityPerformPress()
  }

  func fill(_ element: ScreenAccessibility, value: String) throws {
    let field = try XCTUnwrap(
      (element.object as? NSTextField) ?? (element.object as? NSCell)?.controlView as? NSTextField)
    controller.window?.makeFirstResponder(field)
    field.stringValue = value
    field.currentEditor()?.string = value
    field.delegate?.controlTextDidChange?(
      Notification(name: NSControl.textDidChangeNotification, object: field))
  }

  func snapshot(_ name: String) throws {
    guard let view = controller.window?.contentView else {
      return XCTFail("Missing native content view")
    }
    view.layoutSubtreeIfNeeded()
    XCTAssertGreaterThanOrEqual(view.bounds.width, 600)
    XCTAssertLessThanOrEqual(view.bounds.width, 640)
    XCTAssertGreaterThan(view.bounds.height, 60)
    let representation = try XCTUnwrap(view.bitmapImageRepForCachingDisplay(in: view.bounds))
    view.cacheDisplay(in: view.bounds, to: representation)
    let png = try XCTUnwrap(representation.representation(using: .png, properties: [:]))
    XCTAssertGreaterThan(png.count, 1000)
    if let folder = ProcessInfo.processInfo.environment["COMPANION_SNAPSHOT_DIR"] {
      let output = URL(fileURLWithPath: folder)
      try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
      try png.write(to: output.appendingPathComponent(name + ".png"))
    }
  }

  func close() {
    try? snapshot("screen-" + suite)
    if let folder = ProcessInfo.processInfo.environment["COMPANION_SNAPSHOT_DIR"] {
      try? elements().map(\.diagnostic).joined(separator: "\n").write(
        to: URL(fileURLWithPath: folder).appendingPathComponent("tree-" + suite + ".txt"),
        atomically: true, encoding: .utf8)
    }
    controller.close()
    defaults.removePersistentDomain(forName: suite)
    NSApplication.shared.setActivationPolicy(originalPolicy)
  }
}

@MainActor final class NativeScreenTests: XCTestCase {
  func testFullSettingsWindowRendersBoundedScrollLayoutForEverySection() async throws {
    let f = try AppTestFixture()
    try f.loadManaged()
    defer { f.close() }
    for section in ["installation", "mcps", "general"] {
      f.model.settingsSection = section
      let screen = TestScreen(model: f.model, fullSettings: true)
      defer { screen.close() }
      try await f.waitFor {
        screen.elements().contains { $0.object is NSScrollView }
      }
      let content = try XCTUnwrap(screen.controller.window?.contentView)
      XCTAssertLessThanOrEqual(content.bounds.height, NSScreen.main?.visibleFrame.height ?? 1200)
      try screen.snapshot("full-settings-" + section)
    }
    XCTAssertTrue(f.actions.allSatisfy { $0 == "prerequisites" })
  }

  func testOnboardingConnectUsesTheRenderedTextFieldAndButton() async throws {
    let f = try AppTestFixture()
    f.model.hasLoaded = true
    let screen = TestScreen(model: f.model, onboarding: true)
    defer {
      screen.close()
      f.close()
    }
    try await f.waitFor { screen.allText.contains("Keep your existing OpenMaskit") }
    // AppKit's bridged text-field cell does not forward SwiftUI identifiers on
    // every supported OS. Locate the unique visible field by role and value.
    let address = try screen.element(named: "http://127.0.0.1:9473", role: .textField)
    XCTAssertEqual(address.accessibilityRole(), .textField)
    try screen.fill(address, value: "http://127.0.0.1:19476")
    try await f.waitFor { (address.accessibilityValue() as? String) == "http://127.0.0.1:19476" }
    screen.press(try screen.element(id: "setup.connect"))
    try await f.waitFor { f.actions.contains("status") && !f.model.busy }
    XCTAssertEqual(f.actions, ["connect-existing", "status"])
    XCTAssertEqual(f.calls()[0]["arguments"] as? [String], ["--url", "http://127.0.0.1:19476"])
    XCTAssertTrue(f.opened.isEmpty)
    try screen.snapshot("onboarding-connected")
  }

  func testManagedOnboardingShowsMissingRequirementsAndAllowsRepair() async throws {
    let f = try AppTestFixture()
    f.model.hasLoaded = true
    f.replies["prerequisites"] = ["body": AppTestFixture.requirements(missing: "desktop")]
    try f.save()
    let screen = TestScreen(model: f.model, onboarding: true)
    defer {
      screen.close()
      f.close()
    }
    try await f.waitFor { screen.allText.contains("Keep your existing OpenMaskit") }
    screen.press(try screen.element(named: "Companion installation", role: .radioButton))
    try await f.waitFor { f.model.requirements?.ready == false && !f.model.checkingRequirements }
    XCTAssertFalse(try screen.element(id: "setup.managed").isAccessibilityEnabled())
    XCTAssertTrue(screen.allText.contains("Needs attention"))
    XCTAssertFalse(f.actions.contains("prepare-managed"))
    try screen.snapshot("onboarding-requirements-missing")
    f.replies["prerequisites"] = ["body": AppTestFixture.requirements()]
    try f.save()
    screen.press(try screen.element(named: "Check Again", role: .button))
    try await f.waitFor { f.model.requirements?.ready == true && !f.model.checkingRequirements }
    screen.press(try screen.element(id: "setup.managed"))
    try await f.waitFor { f.model.installation.configured && !f.model.busy }
    XCTAssertTrue(f.actions.contains("prepare-managed"))
    XCTAssertTrue(f.actions.contains("start"))
    XCTAssertTrue(f.opened.isEmpty)
  }

  func testSettingsTabsAndStartupToggleUseNativeAccessibilityActions() async throws {
    let f = try AppTestFixture()
    try f.loadManaged()
    let screen = TestScreen(model: f.model)
    defer {
      screen.close()
      f.close()
    }
    try await f.waitFor { screen.allText.contains("Current installation") }
    screen.press(try screen.element(named: "General", role: .radioButton))
    try await f.waitFor { screen.allText.contains("Startup & updates") }
    XCTAssertTrue(screen.allText.contains("Start services and local MCPs when Companion opens"))
    let toggle = try XCTUnwrap(
      screen.elements().first {
        $0.accessibilityRole() == .checkBox && $0.supportsPress
      }, "Missing native startup switch")
    XCTAssertTrue(screen.preferences.automaticallyStartServices)
    screen.press(toggle)
    try await f.waitFor { !screen.preferences.automaticallyStartServices }
    XCTAssertFalse(screen.defaults.bool(forKey: "automaticallyStartServices"))
    XCTAssertFalse(
      AppPreferences(defaults: screen.defaults, activate: {}).automaticallyStartServices)
    try screen.snapshot("settings-general")
    screen.press(try screen.element(named: "Local MCPs", role: .radioButton))
    try await f.waitFor { screen.allText.contains("No local MCP profiles added yet.") }
    XCTAssertFalse(
      try screen.element(named: "Add Local MCP…", role: .button).isAccessibilityEnabled())
    try screen.snapshot("settings-local-mcps-unpaired")
    XCTAssertTrue(f.actions.allSatisfy { $0 == "prerequisites" })
  }

  func testLocalMCPRegistrationUsesTheRenderedButtonAndRequiresAConnector() async throws {
    let f = try AppTestFixture()
    try f.loadManaged(paired: true)
    f.model.settingsSection = "mcps"
    f.model.profiles = [LocalProfile(id: "fixture", name: "Synthetic MCP")]
    let screen = TestScreen(model: f.model)
    defer {
      screen.close()
      f.close()
    }
    try await f.waitFor { screen.allText.contains("Synthetic MCP") }
    XCTAssertFalse(
      try screen.element(named: "Add to OpenMaskit", role: .button).isAccessibilityEnabled())
    f.model.connectorRunning = true
    try await f.waitFor {
      (try? screen.element(named: "Add to OpenMaskit", role: .button).isAccessibilityEnabled())
        == true
    }
    screen.press(try screen.element(named: "Add to OpenMaskit", role: .button))
    try await f.waitFor { f.actions.contains("status") && !f.model.busy }
    XCTAssertEqual(f.calls()[0]["arguments"] as? [String], ["fixture", "--name", "Synthetic MCP"])
    XCTAssertEqual(f.model.message, "MCP added. Configure its checks in OpenMaskit.")
    try screen.snapshot("settings-local-mcp-registered")
  }

  func testSettingsCheckAndDashboardButtonsUseAFreshVerifiedBackendResponse() async throws {
    let f = try AppTestFixture()
    try f.loadManaged()
    f.replies["status"] = ["body": AppTestFixture.state(mode: "managed")]
    f.replies["dashboard"] = ["body": ["ready": true, "dashboard": "http://127.0.0.1:19473"]]
    try f.save()
    let screen = TestScreen(model: f.model)
    defer {
      screen.close()
      f.close()
    }
    try await f.waitFor { screen.allText.contains("Current installation") }
    screen.press(try screen.element(id: "settings.checkConnection"))
    try await f.waitFor { f.actions.contains("profiles") && f.model.hasLoaded }
    screen.press(try screen.element(id: "settings.dashboard"))
    try await f.waitFor { !f.opened.isEmpty }
    XCTAssertEqual(f.opened.first?.absoluteString, "http://127.0.0.1:19473")
    try screen.snapshot("settings-installation-ready")
  }

  func testBusyAndErrorScreensRenderReadableFeedbackAndDisableActions() async throws {
    let f = try AppTestFixture()
    try f.loadManaged()
    f.model.busy = true
    f.model.progress = "Starting the synthetic services and checking their connection."
    let screen = TestScreen(model: f.model)
    defer {
      screen.close()
      f.close()
    }
    try await f.waitFor { screen.allText.contains("Starting the synthetic services") }
    XCTAssertFalse(try screen.element(id: "settings.dashboard").isAccessibilityEnabled())
    XCTAssertFalse(try screen.element(id: "settings.checkConnection").isAccessibilityEnabled())
    try screen.snapshot("settings-busy")
    f.model.busy = false
    f.model.progress = ""
    f.model.message = "The synthetic service is unavailable. Check its connection and retry."
    try await f.waitFor { screen.allText.contains("The synthetic service is unavailable.") }
    try screen.snapshot("settings-error")
    XCTAssertTrue(f.actions.allSatisfy { $0 == "prerequisites" })
  }

  func testExistingInstallationScreenDoesNotExposeManagedMCPApproval() async throws {
    let f = try AppTestFixture()
    await f.model.refresh()
    f.model.settingsSection = "mcps"
    let screen = TestScreen(model: f.model)
    defer {
      screen.close()
      f.close()
    }
    try await f.waitFor { screen.allText.contains("Manage your existing MCP servers") }
    XCTAssertFalse(screen.elements().contains { screen.text($0).contains("Add Local MCP…") })
    XCTAssertTrue(
      try screen.element(named: "Open OpenMaskit", role: .button).isAccessibilityEnabled())
    try screen.snapshot("settings-existing-installation")
  }
}
