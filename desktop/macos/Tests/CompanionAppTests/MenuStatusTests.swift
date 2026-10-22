import CompanionPolicy
import Foundation
import XCTest

@testable import OpenMaskitCompanion

@MainActor final class MenuStatusTests: XCTestCase {
  func configuredModel() -> CompanionModel {
    let model = CompanionModel()
    model.installation.mode = .managed
    model.installation.configured = true
    model.installation.canManageServices = true
    model.installation.dashboard = "http://127.0.0.1:9493"
    model.hasLoaded = true
    return model
  }

  func testInitialLoadAndFailureUseShortStatusLabels() {
    let model = CompanionModel()
    XCTAssertEqual(model.menuStatus, .checking)
    model.message = "A long failure explanation belongs in Settings."
    XCTAssertEqual(model.menuStatus, .needsAttention)
    XCTAssertTrue(model.menuStatus.offersDetails)
    model.hasLoaded = true
    XCTAssertEqual(model.menuStatus, .setupRequired)
  }

  func testBusyStatusNeverExpandsIntoTheFullProgressMessage() {
    let model = configuredModel()
    model.busy = true
    model.progress = String(repeating: "Long installation progress ", count: 50)
    XCTAssertEqual(model.menuStatus.rawValue, "Working…")
  }

  func testStoppedAndPartiallyRunningServicesHaveDistinctStatuses() {
    let model = configuredModel()
    XCTAssertEqual(model.menuStatus, .stopped)
    model.installation.services = [
      ServiceState(name: "openmaskit", state: "running", health: "starting")
    ]
    XCTAssertEqual(model.menuStatus, .needsAttention)
  }

  func testHealthyServicesAndSuccessMessagesProduceOneReadyStatus() {
    let model = configuredModel()
    model.installation.services = ["openmaskit", "presidio-analyzer", "connector-relay"].map {
      ServiceState(name: $0, state: "running", health: "healthy")
    }
    model.message = "Services and the connector are ready."
    model.installation.ready = true
    model.installation.health = "healthy"
    XCTAssertEqual(model.menuStatus, .ready)
    XCTAssertFalse(model.menuStatus.offersDetails)
  }

  func testUnavailableOrDegradedDashboardIsNotHiddenByHealthyContainers() {
    let model = configuredModel()
    model.installation.services = ["openmaskit", "presidio-analyzer", "connector-relay"].map {
      ServiceState(name: $0, state: "running", health: "healthy")
    }
    XCTAssertEqual(model.menuStatus, .needsAttention)
    model.installation.ready = true
    model.installation.health = "degraded"
    XCTAssertEqual(model.menuStatus, .needsAttention)
  }

  func testUnresponsivePairedLocalMCPRequiresAttention() {
    let model = configuredModel()
    model.installation.services = ["openmaskit", "presidio-analyzer", "connector-relay"].map {
      ServiceState(name: $0, state: "running", health: "healthy")
    }
    model.installation.paired = true
    model.profiles = [LocalProfile(id: "fixture", name: "Synthetic MCP")]
    XCTAssertEqual(model.menuStatus, .needsAttention)
  }

  func testRuntimeFailuresRemainVisibleWithoutDumpingDetails() throws {
    let model = configuredModel()
    let json = """
      {"ready":false,"checks":[{"id":"desktop","title":"Docker Desktop",
      "state":"needs_attention","detail":"A detailed repair instruction in Settings."}]}
      """
    model.requirements = try JSONDecoder().decode(RuntimeRequirements.self, from: Data(json.utf8))
    XCTAssertEqual(model.menuStatus, .needsAttention)
    XCTAssertTrue(model.menuStatus.offersDetails)
    model.requirements = nil
    model.installation.error = "Docker is unavailable"
    XCTAssertEqual(model.menuStatus, .needsAttention)
    model.installation.error = nil
    model.installation.connectionError = "Connection failed"
    XCTAssertEqual(model.menuStatus, .needsAttention)
  }

  func testExternalInstallationStatusesDoNotDependOnManagedServices() {
    let model = configuredModel()
    model.installation.mode = .existing
    model.installation.canManageServices = false
    XCTAssertEqual(model.menuStatus, .unavailable)
    XCTAssertTrue(model.menuStatus.offersDetails)
    model.installation.ready = true
    model.installation.health = "healthy"
    XCTAssertEqual(model.menuStatus, .ready)
    model.installation.health = "degraded"
    XCTAssertEqual(model.menuStatus, .needsAttention)
  }
}
