import CompanionDesktopCore
import CompanionPolicy
import Foundation

@main enum StartupAcceptance {
  @MainActor static func main() async throws {
    var state = InstallationState()
    state.mode = .managed
    state.configured = true
    state.paired = true
    state.ready = true
    state.dashboard = "http://127.0.0.1:9493"
    state.services = ["openmaskit", "presidio-analyzer", "connector-relay"].map {
      ServiceState(name: $0, state: "running", health: "healthy")
    }
    var events: [String] = []
    var dockerReady = false
    let actions = StartupActions(
      dockerReady: { events.append("probe"); return dockerReady },
      openDocker: { events.append("openDocker"); dockerReady = true },
      startDependencies: { events.append("dependencies") },
      startConnector: { events.append("connector") },
      connectorReady: { events.append("connected"); return true },
      startOpenMaskit: { events.append("openmaskit") },
      refreshConnections: { events.append("restore") },
      waitForServices: { events.append("verify"); return state },
      pause: {}, progress: { _ in })
    let startup = ServiceStartup()
    let result = try await startup.onLaunch(state: state, enabled: true, approvedProfiles: 1, actions: actions)
    precondition(result?.canOpenDashboard == true)
    precondition(events == ["probe", "openDocker", "probe", "dependencies", "connector", "connected", "openmaskit", "restore", "verify"])
    events = []
    let repeated = try await startup.onLaunch(state: state, enabled: true, approvedProfiles: 1, actions: actions)
    precondition(repeated == nil && events.isEmpty, "A manual stop must survive monitoring and window reopen")
    for mode in [InstallationState.Mode.unconfigured, .existing] {
      var other = state
      other.mode = mode
      let skipped = try await ServiceStartup().onLaunch(state: other, enabled: true, approvedProfiles: 1, actions: actions)
      precondition(skipped == nil && events.isEmpty)
    }
    let disabled = try await ServiceStartup().onLaunch(state: state, enabled: false, approvedProfiles: 1, actions: actions)
    precondition(disabled == nil && events.isEmpty)
    var timeout = actions
    var probes = 0
    timeout.dockerReady = { probes += 1; return false }
    do {
      _ = try await ServiceStartup.start(state: state, approvedProfiles: 1, actions: timeout)
      preconditionFailure("Expected bounded Docker timeout")
    } catch { precondition(probes == 61) }
    let pipes = try await BackendProcess.run(executable: URL(fileURLWithPath: "/bin/sh"),
      arguments: ["-c", "i=0; while [ $i -lt 10000 ]; do printf synthetic; printf diagnostic >&2; i=$((i+1)); done"], timeout: 5)
    precondition(pipes.status == 0 && pipes.output.count == 90000 && pipes.errors.count == 100000)
    do {
      _ = try await BackendProcess.run(executable: URL(fileURLWithPath: "/bin/sleep"), arguments: ["5"], timeout: 0.05)
      preconditionFailure("Expected child timeout")
    } catch { precondition(error is BackendFailure) }
    do {
      _ = try await BackendProcess.run(executable: URL(fileURLWithPath: "/usr/bin/printf"), arguments: ["%080000d", "1"], outputLimit: 64)
      preconditionFailure("Expected output limit")
    } catch { precondition(error is BackendFailure) }
    print("PASS: automatic startup ordering, menu-only lifecycle policy, opt-out, external/fresh guards, manual stops and bounded Docker wait")
    print("PASS: concurrent helper output/error drainage, bounded output and child timeout")
  }
}
