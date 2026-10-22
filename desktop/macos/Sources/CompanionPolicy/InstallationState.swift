import Foundation

public struct InstallationState: Codable {
  public enum Mode: String, Codable { case unconfigured, existing, managed }
  public var mode: Mode = .unconfigured
  public var configured = false
  public var initialized = false
  public var ready = false
  public var paired = false
  public var canManageServices = false
  public var dashboard: String?
  public var health = "offline"
  public var serverCount = 0
  public var services: [ServiceState] = []
  public var connectors: [ConnectorState]?
  public var error: String?
  public var connectionError: String?

  enum CodingKeys: String, CodingKey {
    case mode, configured, initialized, ready, paired, dashboard, health, services, connectors,
      error
    case canManageServices = "can_manage_services"
    case serverCount = "server_count"
    case connectionError = "connection_error"
  }

  public init() {}
  public var needsOnboarding: Bool { !configured }
  public var canOpenDashboard: Bool { configured && ready && dashboardURL != nil }
  public var canUseLocalConnector: Bool { mode == .managed && configured && ready }
  public var servicesAreHealthy: Bool {
    mode == .managed
      && ["openmaskit", "presidio-analyzer", "connector-relay"].allSatisfy { name in
        services.contains { $0.name == name && $0.state == "running" && $0.health == "healthy" }
      }
  }
  public var dashboardURL: URL? { dashboard.flatMap(Self.localDashboardURL) }
  public var title: String {
    if ready { return health == "healthy" ? "Connected" : "Connected · needs attention" }
    if mode == .existing { return "Existing installation unavailable" }
    if error != nil { return "Check Docker Desktop" }
    return services.contains(where: { $0.state == "running" })
      ? "Services need attention" : "Services are stopped"
  }

  /// The browser only receives a checked local origin, never a response-supplied link.
  public static func localDashboardURL(_ value: String) -> URL? {
    guard let parts = URLComponents(string: value),
      let scheme = parts.scheme, ["http", "https"].contains(scheme),
      let host = parts.host?.lowercased(), parts.user == nil, parts.password == nil,
      parts.path.isEmpty || parts.path == "/", parts.query == nil, parts.fragment == nil,
      (1...65535).contains(parts.port ?? (scheme == "https" ? 443 : 80))
    else { return nil }
    let octets = host.split(separator: ".", omittingEmptySubsequences: false)
    let ipv4 =
      octets.count == 4 && octets.first == "127"
      && octets.allSatisfy { Int($0).map { (0...255).contains($0) } ?? false }
    guard ipv4 || ["localhost", "::1", "[::1]"].contains(host) else { return nil }
    return parts.url
  }
}

public struct ServiceState: Codable, Identifiable {
  public var id: String { name }
  public let name: String
  public let state: String
  public let health: String
  public init(name: String, state: String, health: String) {
    self.name = name
    self.state = state
    self.health = health
  }
  public var title: String {
    switch name {
    case "openmaskit": return "OpenMaskit"
    case "presidio-analyzer": return "Presidio"
    default: return "Local MCP connection"
    }
  }
}

public struct ConnectorState: Codable, Identifiable {
  public let id: String
  public let name: String
  public let connected: Bool
}

public struct RuntimeRequirements: Codable {
  public let ready: Bool
  public let checks: [RuntimeRequirement]
  public var issue: String? {
    checks.first { $0.state == "needs_attention" }?.detail
  }
  public var canStartDocker: Bool {
    !checks.isEmpty && checks.filter { $0.id != "daemon" }.allSatisfy { $0.state == "ready" }
  }
}

public struct RuntimeRequirement: Codable, Identifiable {
  public let id: String
  public let title: String
  public let state: String
  public let detail: String
}
