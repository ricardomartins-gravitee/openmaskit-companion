import CompanionPolicy
import XCTest

@testable import CompanionDesktopCore

@MainActor final class StartupHarness {
  var events: [String] = []
  var dockerProbe = 0
  var dockerReadyAfter = 0
  var connectorProbe = 0
  var connectorReadyAfter = 0
  var failDependencies = false
  var healthy = true
  var state: InstallationState {
    var state = InstallationState()
    state.mode = .managed
    state.configured = true
    state.paired = true
    state.ready = healthy
    state.dashboard = "http://127.0.0.1:9493"
    state.services = ["openmaskit", "presidio-analyzer", "connector-relay"].map {
      ServiceState(name: $0, state: "running", health: "healthy")
    }
    return state
  }
  var actions: StartupActions {
    StartupActions(
      dockerReady: {
        self.events.append("docker")
        self.dockerProbe += 1
        return self.dockerProbe > self.dockerReadyAfter
      },
      openDocker: { self.events.append("openDocker") },
      startDependencies: {
        self.events.append("dependencies")
        if self.failDependencies { throw StartupFailure.servicesUnavailable }
      },
      startConnector: { self.events.append("connector") },
      connectorReady: {
        self.events.append("connectorReady")
        self.connectorProbe += 1
        return self.connectorProbe > self.connectorReadyAfter
      },
      startOpenMaskit: { self.events.append("openmaskit") },
      refreshConnections: { self.events.append("restore") },
      waitForServices: {
        self.events.append("verify")
        return self.state
      },
      pause: { self.events.append("wait") }, progress: { _ in })
  }
}

@MainActor final class ServiceStartupTests: XCTestCase {
  func testOrderStartsRelayAndConnectorBeforeOpenMaskitAndRestoresSessions() async throws {
    let harness = StartupHarness()
    let startup = ServiceStartup()
    let result = try await startup.onLaunch(
      state: harness.state, enabled: true, approvedProfiles: 1, actions: harness.actions)
    XCTAssertTrue(result?.canOpenDashboard == true)
    XCTAssertEqual(
      harness.events,
      ["docker", "dependencies", "connector", "connectorReady", "openmaskit", "restore", "verify"])
    harness.events = []
    let repeated = try await startup.onLaunch(
      state: harness.state, enabled: true, approvedProfiles: 1, actions: harness.actions)
    XCTAssertNil(repeated)
    XCTAssertTrue(
      harness.events.isEmpty, "Reopening windows or monitoring must not undo manual stops")
  }

  func testDisabledExternalAndUnconfiguredLaunchesDoNothing() async throws {
    for kind in ["disabled", "external", "fresh"] {
      let harness = StartupHarness()
      var state = harness.state
      if kind == "external" { state.mode = .existing }
      if kind == "fresh" { state.configured = false }
      let result = try await ServiceStartup().onLaunch(
        state: state, enabled: kind != "disabled", approvedProfiles: 1, actions: harness.actions)
      XCTAssertNil(result)
      XCTAssertTrue(harness.events.isEmpty)
    }
  }

  func testRelaySecurityUpgradeBlocksAutomaticAndManualStartupBeforeSideEffects() async {
    let harness = StartupHarness()
    var state = harness.state
    state.relayTLS = false

    do {
      let result = try await ServiceStartup().onLaunch(
        state: state, enabled: true, approvedProfiles: 1, actions: harness.actions)
      XCTAssertNil(result)
    } catch {
      XCTFail("Automatic startup should be skipped while relay TLS needs an upgrade: \(error)")
    }
    XCTAssertTrue(harness.events.isEmpty)

    do {
      _ = try await ServiceStartup.start(
        state: state, approvedProfiles: 1, actions: harness.actions)
      XCTFail("Manual startup should require a relay security upgrade")
    } catch let failure as StartupFailure {
      guard case .relaySecurityUpdate = failure else {
        return XCTFail("Expected relay security upgrade failure, got \(failure)")
      }
    } catch {
      XCTFail("Expected relay security upgrade failure, got \(error)")
    }
    XCTAssertTrue(harness.events.isEmpty, "Upgrade guard must run before Docker or service actions")
  }

  func testDockerOpensOnceThenWaitsForReadiness() async throws {
    let harness = StartupHarness()
    harness.dockerReadyAfter = 2
    _ = try await ServiceStartup.start(
      state: harness.state, approvedProfiles: 1, actions: harness.actions)
    XCTAssertEqual(harness.events.filter { $0 == "openDocker" }.count, 1)
    XCTAssertEqual(
      Array(harness.events.prefix(6)), ["docker", "openDocker", "wait", "docker", "wait", "docker"])
  }

  func testDockerTimeoutIsBoundedAndDoesNotStartAnything() async {
    let harness = StartupHarness()
    harness.dockerReadyAfter = 1000
    do {
      _ = try await ServiceStartup.start(
        state: harness.state, approvedProfiles: 1, actions: harness.actions)
      XCTFail("Expected Docker timeout")
    } catch { XCTAssertTrue(error is StartupFailure) }
    XCTAssertEqual(harness.dockerProbe, 61)
    XCTAssertFalse(harness.events.contains("dependencies"))
  }

  func testSlowProbesRespectElapsedTimeAsWellAsIterationLimit() async {
    let harness = StartupHarness()
    harness.dockerReadyAfter = 1000
    var instant = ContinuousClock.now
    var actions = harness.actions
    actions.now = { instant }
    actions.pause = { instant = instant.advanced(by: .seconds(121)) }
    do {
      _ = try await ServiceStartup.start(
        state: harness.state, approvedProfiles: 1, actions: actions)
      XCTFail("Expected elapsed-time deadline")
    } catch {}
    XCTAssertEqual(harness.dockerProbe, 1)
    XCTAssertFalse(harness.events.contains("dependencies"))
  }

  func testDependencyFailureDoesNotLaunchConnector() async {
    let harness = StartupHarness()
    harness.failDependencies = true
    do {
      _ = try await ServiceStartup.start(
        state: harness.state, approvedProfiles: 1, actions: harness.actions)
      XCTFail("Expected dependency failure")
    } catch {}
    XCTAssertFalse(harness.events.contains("connector"))
    XCTAssertFalse(harness.events.contains("openmaskit"))
  }

  func testUnpairedOrUnapprovedDoesNotLaunchProgramsOrApproveAnything() async throws {
    for paired in [false, true] {
      let harness = StartupHarness()
      var state = harness.state
      state.paired = paired
      _ = try await ServiceStartup.start(
        state: state, approvedProfiles: paired ? 0 : 1, actions: harness.actions)
      XCTAssertFalse(harness.events.contains("connector"))
      XCTAssertFalse(harness.events.contains("restore"))
      XCTAssertTrue(harness.events.contains("openmaskit"))
    }
  }

  func testOfflineConnectorDoesNotStartOpenMaskitOrLoopForever() async {
    let harness = StartupHarness()
    harness.connectorReadyAfter = 1000
    do {
      _ = try await ServiceStartup.start(
        state: harness.state, approvedProfiles: 1, actions: harness.actions)
      XCTFail("Expected connector timeout")
    } catch {}
    XCTAssertEqual(harness.connectorProbe, 15)
    XCTAssertFalse(harness.events.contains("openmaskit"))
  }

  func testUnavailableServicesDoNotReportSuccess() async {
    let harness = StartupHarness()
    harness.healthy = false
    do {
      _ = try await ServiceStartup.start(
        state: harness.state, approvedProfiles: 1, actions: harness.actions)
      XCTFail("Expected health failure")
    } catch { XCTAssertTrue(error is StartupFailure) }
  }
}
