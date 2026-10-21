import CompanionPolicy
import Foundation

public enum StartupFailure: LocalizedError {
  case dockerUnavailable, connectorUnavailable, servicesUnavailable
  public var errorDescription: String? {
    switch self {
    case .dockerUnavailable:
      return "Docker did not become ready. Check Docker Desktop, then try Start All again."
    case .connectorUnavailable:
      return "The local connector could not connect. Check pairing in Settings."
    case .servicesUnavailable: return "Services need attention. Check their status in Settings."
    }
  }
}

@MainActor public struct StartupActions {
  public var dockerReady: () async throws -> Bool
  public var openDocker: () async throws -> Void
  public var startDependencies: () async throws -> Void
  public var startConnector: () async throws -> Void
  public var connectorReady: () async throws -> Bool
  public var startOpenMaskit: () async throws -> Void
  public var refreshConnections: () async throws -> Void
  public var waitForServices: () async throws -> InstallationState
  public var pause: () async throws -> Void
  public var progress: (String) -> Void
  public var now: () -> ContinuousClock.Instant

  public init(
    dockerReady: @escaping () async throws -> Bool,
    openDocker: @escaping () async throws -> Void,
    startDependencies: @escaping () async throws -> Void,
    startConnector: @escaping () async throws -> Void,
    connectorReady: @escaping () async throws -> Bool,
    startOpenMaskit: @escaping () async throws -> Void,
    refreshConnections: @escaping () async throws -> Void,
    waitForServices: @escaping () async throws -> InstallationState,
    pause: @escaping () async throws -> Void = { try await Task.sleep(for: .seconds(2)) },
    progress: @escaping (String) -> Void,
    now: @escaping () -> ContinuousClock.Instant = { .now }
  ) {
    self.dockerReady = dockerReady
    self.openDocker = openDocker
    self.startDependencies = startDependencies
    self.startConnector = startConnector
    self.connectorReady = connectorReady
    self.startOpenMaskit = startOpenMaskit
    self.refreshConnections = refreshConnections
    self.waitForServices = waitForServices
    self.pause = pause
    self.progress = progress
    self.now = now
  }
}

/// Launch is attempted once. Monitoring/reopening a window never undoes a manual stop.
@MainActor public final class ServiceStartup {
  public private(set) var launchAttempted = false
  public init() {}

  public func onLaunch(
    state: InstallationState, enabled: Bool, approvedProfiles: Int, actions: StartupActions
  ) async throws -> InstallationState? {
    guard !launchAttempted else { return nil }
    launchAttempted = true
    guard enabled && state.configured && state.mode == .managed else { return nil }
    return try await Self.start(state: state, approvedProfiles: approvedProfiles, actions: actions)
  }

  public static func start(
    state: InstallationState, approvedProfiles: Int, actions: StartupActions
  ) async throws -> InstallationState {
    guard state.configured && state.mode == .managed else { return state }
    try Task.checkCancellation()
    actions.progress("Checking Docker…")
    if try await !actions.dockerReady() {
      actions.progress("Opening Docker Desktop…")
      try await actions.openDocker()
      var ready = false
      let deadline = actions.now().advanced(by: .seconds(120))
      for _ in 0..<60 {
        if actions.now() >= deadline { break }
        try await actions.pause()
        if actions.now() >= deadline { break }
        if try await actions.dockerReady() {
          ready = true
          break
        }
      }
      guard ready else { throw StartupFailure.dockerUnavailable }
    }
    try Task.checkCancellation()
    actions.progress("Starting Presidio and the relay…")
    try await actions.startDependencies()
    let connect = state.paired && approvedProfiles > 0
    if connect {
      actions.progress("Connecting this Mac…")
      try await actions.startConnector()
      var ready = false
      let deadline = actions.now().advanced(by: .seconds(30))
      for _ in 0..<15 {
        try Task.checkCancellation()
        if actions.now() >= deadline { break }
        if try await actions.connectorReady() {
          ready = true
          break
        }
        try await actions.pause()
      }
      guard ready else { throw StartupFailure.connectorUnavailable }
    }
    actions.progress("Starting OpenMaskit…")
    try await actions.startOpenMaskit()
    if connect {
      try Task.checkCancellation()
      actions.progress("Restoring local MCP connections…")
      try await actions.refreshConnections()
    }
    actions.progress("Checking all services…")
    let result = try await actions.waitForServices()
    guard result.canOpenDashboard && result.servicesAreHealthy else {
      throw StartupFailure.servicesUnavailable
    }
    return result
  }
}
