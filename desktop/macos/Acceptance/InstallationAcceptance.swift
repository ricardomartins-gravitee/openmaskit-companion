import Foundation

@main enum InstallationAcceptance {
  static func main() throws {
    var state = InstallationState()
    precondition(state.needsOnboarding && !state.canOpenDashboard && !state.canUseLocalConnector)
    state.mode = .existing
    state.configured = true
    state.dashboard = "http://127.0.0.1:9473"
    precondition(!state.needsOnboarding && !state.canOpenDashboard)
    state.ready = true
    precondition(state.canOpenDashboard && !state.canUseLocalConnector)
    state.mode = .managed
    state.configured = false
    precondition(state.needsOnboarding && !state.canOpenDashboard)
    state.configured = true
    precondition(state.canOpenDashboard && state.canUseLocalConnector)
    for address in ["http://localhost:9473", "http://127.0.0.1:9473", "http://[::1]:9473"] {
      precondition(InstallationState.localDashboardURL(address) != nil)
    }
    for address in [
      "http://remote.invalid", "http://127.evil.invalid", "http://127.0.0.1:9473/path",
      "http://user:secret@127.0.0.1:9473",
    ] {
      precondition(InstallationState.localDashboardURL(address) == nil)
    }
    let json = """
      {"mode":"existing","configured":true,"initialized":false,"ready":true,"paired":false,
      "can_manage_services":false,"dashboard":"http://127.0.0.1:9473","health":"healthy",
      "server_count":2,"services":[],"connectors":[]}
      """
    let decoded = try JSONDecoder().decode(InstallationState.self, from: Data(json.utf8))
    precondition(
      decoded.serverCount == 2 && decoded.canOpenDashboard && !decoded.canUseLocalConnector)
    precondition(decoded.relayTLS == nil && !decoded.needsRelayUpgrade)

    var upgrade = InstallationState()
    upgrade.mode = .managed
    upgrade.configured = true
    upgrade.ready = true
    upgrade.paired = true
    upgrade.relayTLS = false
    upgrade.dashboard = "http://127.0.0.1:9493"
    upgrade.health = "healthy"
    upgrade.services = ["openmaskit", "presidio-analyzer", "connector-relay"].map {
      ServiceState(name: $0, state: "running", health: "healthy")
    }
    precondition(upgrade.needsRelayUpgrade && upgrade.canOpenDashboard)
    precondition(!upgrade.canUseLocalConnector && !upgrade.servicesAreHealthy)
    precondition(upgrade.title == "Relay security update required")
    print(
      "PASS: onboarding, offline reconnect, installation capabilities, safe dashboard URLs and legacy status decoding"
    )
    print(
      "PASS: missing relay TLS blocks local connector use and reports the required security upgrade"
    )
  }
}
