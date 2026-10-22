import Foundation
import XCTest

@testable import CompanionPolicy

final class InstallationStateTests: XCTestCase {
  func testRuntimeRequirementFailuresAndRecovery() throws {
    let json = """
      {"ready":false,"checks":[
        {"id":"desktop","title":"Docker Desktop","state":"needs_attention","detail":"Install Docker Desktop."},
        {"id":"daemon","title":"Docker engine","state":"blocked","detail":"Open Docker Desktop."}]}
      """
    let missing = try JSONDecoder().decode(RuntimeRequirements.self, from: Data(json.utf8))
    XCTAssertFalse(missing.ready)
    XCTAssertFalse(missing.canStartDocker)
    XCTAssertEqual(missing.issue, "Install Docker Desktop.")
    let stopped = json.replacingOccurrences(of: "needs_attention", with: "ready")
      .replacingOccurrences(of: "blocked", with: "needs_attention")
    let waiting = try JSONDecoder().decode(RuntimeRequirements.self, from: Data(stopped.utf8))
    XCTAssertTrue(waiting.canStartDocker)
    XCTAssertEqual(waiting.issue, "Open Docker Desktop.")
    let recovered = stopped.replacingOccurrences(of: "needs_attention", with: "ready")
      .replacingOccurrences(of: "\"ready\":false", with: "\"ready\":true")
    let ready = try JSONDecoder().decode(RuntimeRequirements.self, from: Data(recovered.utf8))
    XCTAssertTrue(ready.ready)
    XCTAssertTrue(ready.canStartDocker)
    XCTAssertNil(ready.issue)
  }

  func testFreshInstallShowsOnboardingAndCannotOpenAnything() {
    let state = InstallationState()
    XCTAssertTrue(state.needsOnboarding)
    XCTAssertFalse(state.canOpenDashboard)
    XCTAssertFalse(state.canUseLocalConnector)
  }

  func testConfiguredOfflineExistingInstallationKeepsItsConnection() {
    var state = InstallationState()
    state.mode = .existing
    state.configured = true
    state.dashboard = "http://127.0.0.1:9473"
    XCTAssertFalse(state.needsOnboarding)
    XCTAssertFalse(state.canOpenDashboard)
    XCTAssertFalse(state.canUseLocalConnector)
    state.ready = true
    XCTAssertTrue(state.canOpenDashboard)
    XCTAssertFalse(state.canUseLocalConnector)
  }

  func testPreparedSetupIsIncompleteUntilReadyAndConfigured() {
    var state = InstallationState()
    state.mode = .managed
    state.initialized = true
    state.dashboard = "http://127.0.0.1:9493"
    state.ready = true
    XCTAssertTrue(state.needsOnboarding)
    XCTAssertFalse(state.canOpenDashboard)
    state.configured = true
    XCTAssertFalse(state.needsOnboarding)
    XCTAssertTrue(state.canOpenDashboard)
    XCTAssertTrue(state.canUseLocalConnector)
    state.ready = false
    XCTAssertFalse(state.canUseLocalConnector)
  }

  func testBrowserOnlyAcceptsLocalDashboardOrigins() {
    for value in [
      "http://127.0.0.1:9473", "http://localhost:9473", "https://[::1]:9473",
      "http://127.0.0.2:9473",
    ] {
      XCTAssertNotNil(InstallationState.localDashboardURL(value), value)
    }
    for value in [
      "https://example.com", "http://127.evil.invalid", "http://user:secret@127.0.0.1:9473",
      "http://127.0.0.1:9473/path", "http://127.0.0.1:9473?token=secret", "file:///etc/passwd",
      "http://127.0.0.1:0",
    ] {
      XCTAssertNil(InstallationState.localDashboardURL(value), value)
    }
  }

  func testPublicBackendStatusDecodesWithoutLosingTheSelectedEndpoint() throws {
    let json = """
      {"mode":"existing","configured":true,"initialized":false,"ready":true,"paired":false,
      "can_manage_services":false,"dashboard":"http://127.0.0.1:9473","health":"degraded",
      "server_count":2,"services":[],"connectors":[]}
      """
    let state = try JSONDecoder().decode(InstallationState.self, from: Data(json.utf8))
    XCTAssertTrue(state.canOpenDashboard)
    XCTAssertEqual(state.dashboardURL?.port, 9473)
    XCTAssertEqual(state.serverCount, 2)
    XCTAssertEqual(state.title, "Connected · needs attention")
    XCTAssertFalse(state.canManageServices)
  }
}
