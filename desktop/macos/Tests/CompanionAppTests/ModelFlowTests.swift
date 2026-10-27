import Foundation
import XCTest

@testable import OpenMaskitCompanion

@MainActor final class ModelFlowTests: XCTestCase {
  func testRefreshExistingNeverChecksDockerOrReadsManagedProfiles() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    var loaded = 0
    f.model.didLoad = { loaded += 1 }
    await f.model.refresh()
    await f.model.refresh()
    XCTAssertEqual(f.actions, ["status", "status"])
    XCTAssertEqual(loaded, 1)
    XCTAssertTrue(f.model.installation.canOpenDashboard)
    XCTAssertTrue(f.opened.isEmpty)
  }

  func testManagedRefreshLoadsRequirementsAndOnlySafeProfileMetadata() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    f.replies["status"] = ["body": AppTestFixture.state(mode: "managed")]
    f.replies["profiles"] = ["body": ["profiles": [["id": "fixture", "name": "Synthetic MCP"]]]]
    try f.save()
    await f.model.refresh()
    XCTAssertEqual(f.actions, ["status", "prerequisites", "profiles"])
    XCTAssertEqual(f.model.profiles.first?.name, "Synthetic MCP")
    XCTAssertTrue(f.model.requirements?.ready == true)
    XCTAssertEqual(f.model.menuStatus, .ready)
  }

  func testMissingDockerAndRecoveryClearThePriorRepairMessage() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    f.replies["status"] = ["body": AppTestFixture.state(mode: "managed")]
    f.replies["prerequisites"] = ["body": AppTestFixture.requirements(missing: "desktop")]
    try f.save()
    await f.model.refresh()
    XCTAssertEqual(f.model.menuStatus, .needsAttention)
    XCTAssertFalse(f.model.message.isEmpty)
    f.replies["prerequisites"] = ["body": AppTestFixture.requirements()]
    try f.save()
    await f.model.refresh()
    XCTAssertTrue(f.model.message.isEmpty)
    XCTAssertEqual(f.model.menuStatus, .ready)
  }

  func testUnknownAndMalformedHelperFailuresDoNotExposeRawErrors() async throws {
    let errors: [Any] = [
      ["code": "untrusted", "error": "synthetic-private-token"], "synthetic-private-token",
    ]
    for error in errors {
      let f = try AppTestFixture()
      defer { f.close() }
      f.replies["status"] = ["exit": 1, "error": error]
      try f.save()
      await f.model.refresh()
      XCTAssertFalse(f.model.installation.ready)
      XCTAssertFalse(f.model.message.contains("synthetic-private-token"))
      XCTAssertTrue(f.model.message.contains("could not finish"))
      XCTAssertEqual(f.model.menuStatus, .needsAttention)
    }
  }

  func testKnownHelperErrorIsShownAndBusyStateIsReset() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    f.replies["connect-existing"] = [
      "exit": 1, "error": ["code": "unavailable", "error": "Synthetic service unavailable"],
    ]
    try f.save()
    await f.model.connectExisting("http://127.0.0.1:19473")
    XCTAssertEqual(f.model.message, "Synthetic service unavailable")
    XCTAssertFalse(f.model.busy)
    XCTAssertTrue(f.model.progress.isEmpty)
    XCTAssertTrue(f.opened.isEmpty)
  }

  func testCorruptStatusAndProfileRepliesDoNotMarkAnInstallationReady() async throws {
    for action in ["status", "profiles"] {
      let f = try AppTestFixture()
      defer { f.close() }
      f.replies["status"] = ["body": AppTestFixture.state(mode: "managed")]
      f.replies[action] = ["raw": "not-json"]
      try f.save()
      await f.model.refresh()
      XCTAssertFalse(f.model.hasLoaded)
      XCTAssertFalse(f.model.installation.ready)
      XCTAssertFalse(f.model.message.isEmpty)
    }
  }

  func testMissingHelperFailsWithoutTouchingAnInstallation() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    let model = CompanionModel(backend: f.root.appendingPathComponent("missing"), home: f.home)
    await model.refresh()
    XCTAssertFalse(model.installation.ready)
    XCTAssertFalse(model.message.isEmpty)
    XCTAssertTrue(f.calls().isEmpty)
  }

  func testFreshConnectionChecksReadinessAndDoesNotOpenABrowser() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    await f.model.connectExisting("http://127.0.0.1:19473")
    XCTAssertEqual(f.actions, ["connect-existing", "status"])
    XCTAssertEqual(f.calls().first?["arguments"] as? [String], ["--url", "http://127.0.0.1:19473"])
    XCTAssertTrue(f.model.installation.configured)
    XCTAssertTrue(f.opened.isEmpty)
  }

  func testManagedSetupRequiresPrerequisitesBeforeAnyPreparation() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    f.replies["prerequisites"] = ["body": AppTestFixture.requirements(missing: "compose")]
    try f.save()
    await f.model.configureManaged()
    XCTAssertEqual(f.actions, ["prerequisites"])
    XCTAssertFalse(f.model.installation.configured)
    XCTAssertFalse(f.model.busy)
    XCTAssertTrue(f.opened.isEmpty)
  }

  func testManagedSetupRunsInOrderAndDoesNotOpenABrowser() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    await f.model.configureManaged()
    XCTAssertEqual(f.actions, ["prerequisites", "prepare-managed", "start"])
    XCTAssertTrue(f.model.installation.configured)
    XCTAssertEqual(f.model.installation.mode, .managed)
    XCTAssertEqual(f.calls()[1]["arguments"] as? [String], ["--image", AppTestFixture.image])
    XCTAssertTrue(f.opened.isEmpty)
  }

  func testInterruptedSetupLoadsPreparedStateAndSupportsRetry() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    var pending = AppTestFixture.state(mode: "managed", ready: false)
    pending["configured"] = false
    f.replies["start"] = ["exit": 1, "error": ["error": "synthetic failure"]]
    f.replies["status"] = ["body": pending]
    try f.save()
    await f.model.configureManaged()
    XCTAssertTrue(f.model.installation.initialized)
    XCTAssertTrue(f.model.installation.needsOnboarding)
    XCTAssertFalse(f.model.busy)
    f.replies["start"] = ["body": AppTestFixture.state(mode: "managed")]
    try f.save()
    await f.model.configureManaged()
    XCTAssertTrue(f.model.installation.configured)
    XCTAssertEqual(f.actions.filter { $0 == "prepare-managed" }.count, 2)
  }

  func testDashboardUsesAFreshCheckedOriginAndRejectsRedirectedAddresses() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    await f.model.refresh()
    f.replies["dashboard"] = [
      "body": ["ready": true, "dashboard": "https://remote.invalid/private"]
    ]
    try f.save()
    await f.model.openDashboard()
    XCTAssertTrue(f.opened.isEmpty)
    f.replies["dashboard"] = ["body": ["ready": true, "dashboard": "http://127.0.0.1:19473"]]
    try f.save()
    await f.model.openDashboard()
    XCTAssertEqual(f.opened.map(\.absoluteString), ["http://127.0.0.1:19473"])
  }

  func testOfflineDashboardNeverOpensTheLastKnownAddress() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    await f.model.refresh()
    f.replies["dashboard"] = ["exit": 1, "error": ["code": "unavailable", "error": "Unavailable"]]
    try f.save()
    await f.model.openDashboard()
    XCTAssertFalse(f.model.installation.ready)
    XCTAssertTrue(f.opened.isEmpty)
    await f.model.openDashboard()
    XCTAssertEqual(f.actions.filter { $0 == "dashboard" }.count, 1)
  }

  func testBusyOperationsDoNotDoubleSubmitOrRefresh() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    f.model.busy = true
    await f.model.refresh()
    await f.model.connectExisting("http://127.0.0.1:19473")
    await f.model.configureManaged()
    await f.model.action(["register", "fixture", "--name", "Fixture"], success: "done")
    await f.model.startAll()
    XCTAssertTrue(f.calls().isEmpty)
  }

  func testLateRefreshCannotReplaceANewerInstallationSelection() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    f.model.hasLoaded = true
    f.replies["status"] = ["body": AppTestFixture.state(), "wait": "release-old-refresh"]
    try f.save()
    let refresh = Task { await f.model.refresh() }
    try await f.waitFor { f.actions.contains("status") }
    await f.model.refresh()
    XCTAssertEqual(f.actions, ["status"])
    var selected = AppTestFixture.state()
    selected["dashboard"] = "http://127.0.0.1:19475"
    f.replies["status"] = ["body": selected]
    try f.save()
    await f.model.connectExisting("http://127.0.0.1:19475")
    try Data().write(to: f.home.appendingPathComponent("release-old-refresh"))
    await refresh.value
    XCTAssertEqual(f.model.installation.dashboard, "http://127.0.0.1:19475")
    XCTAssertTrue(f.model.message.hasPrefix("Connected."))
  }

  func testRegistrationKeepsArgumentBoundariesAndResetsBusyOnFailure() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    await f.model.action(
      ["register", "fixture", "--name", "Synthetic MCP name"], success: "Registered")
    XCTAssertEqual(
      f.calls().first?["arguments"] as? [String], ["fixture", "--name", "Synthetic MCP name"])
    XCTAssertEqual(f.model.message, "Registered")
    f.replies["register"] = ["exit": 1, "error": ["error": "synthetic-private-token"]]
    try f.save()
    await f.model.action(
      ["register", "fixture", "--name", "Synthetic MCP name"], success: "Registered")
    XCTAssertFalse(f.model.busy)
    XCTAssertFalse(f.model.message.contains("synthetic-private-token"))
  }

  func testConnectorUsesOnlyTheIsolatedBackendAndCanBeStopped() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    try f.loadManaged(paired: true)
    await f.model.toggleConnector()
    try await f.waitFor { f.actions.contains("connect") }
    XCTAssertTrue(f.model.connectorRunning)
    XCTAssertTrue(f.model.connectorIsOnline)
    XCTAssertTrue(f.actions.contains("connect"))
    XCTAssertTrue(f.actions.contains("refresh-connections"))
    await f.model.toggleConnector()
    XCTAssertFalse(f.model.connectorRunning)
    XCTAssertFalse(f.model.connectorIsOnline)
  }

  func testMissingPrerequisitesNeverOpenDockerOrStartServices() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    try f.loadManaged()
    f.replies["prerequisites"] = ["body": AppTestFixture.requirements(missing: "desktop")]
    try f.save()
    await f.model.startAll()
    XCTAssertEqual(f.actions, ["prerequisites"])
    XCTAssertEqual(f.dockerOpened, 0)
    XCTAssertFalse(f.model.busy)
  }

  func testStoppedDockerIsOpenedOnceBeforeStartingInstalledServices() async throws {
    let f = try AppTestFixture()
    defer { f.close() }
    try f.loadManaged()
    f.replies["prerequisites"] = ["body": AppTestFixture.requirements(missing: "daemon")]
    try f.save()
    f.onOpenDocker = {
      f.replies["prerequisites"] = ["body": AppTestFixture.requirements()]
      try f.save()
    }
    await f.model.startAll()
    XCTAssertEqual(f.dockerOpened, 1)
    XCTAssertEqual(
      f.actions,
      [
        "prerequisites", "prerequisites", "start-dependencies", "start-installed", "wait-services",
        "connector-status",
      ])
    XCTAssertTrue(f.model.installation.servicesAreHealthy)
  }
}
