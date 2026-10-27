import AppKit
import Foundation
import XCTest

@testable import OpenMaskitCompanion

/// Real helper processes with synthetic replies; never launches Docker or a user's MCP.
@MainActor final class AppTestFixture {
  let root: URL
  let backend: URL
  let home: URL
  var model: CompanionModel!
  var replies: [String: Any] = [:]
  var opened: [URL] = []
  var dockerOpened = 0
  var onOpenDocker: (() throws -> Void)?
  static let image =
    "ghcr.io/ricardomartins-gravitee/openmaskit-connector@sha256:"
    + String(repeating: "a", count: 64)

  init() throws {
    root = FileManager.default.temporaryDirectory.appendingPathComponent(
      "Companion Test " + UUID().uuidString)
    backend = root.appendingPathComponent("fixture-helper")
    home = root.appendingPathComponent("isolated-home")
    try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
    try Self.script.write(to: backend, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: backend.path)
    replies = [
      "status": ["body": Self.state()],
      "profiles": ["body": ["profiles": []]],
      "prerequisites": ["body": Self.requirements()],
      "connect-existing": ["body": ["configured": true]],
      "prepare-managed": ["body": ["initialized": true]],
      "start": ["body": Self.state(mode: "managed")],
      "wait-services": ["body": Self.state(mode: "managed")],
      "connector-status": ["body": ["connected": true]],
      "refresh-connections": ["body": ["connected": true, "refreshed": 1]],
      "register": ["body": ["connected": true]],
    ]
    try save()
    model = CompanionModel(
      backend: backend, home: home, image: Self.image,
      openDashboard: { [weak self] in self?.opened.append($0) },
      openDocker: { [weak self] in
        guard let self else { return }
        self.dockerOpened += 1
        try self.onOpenDocker?()
      })
  }

  func save() throws {
    try JSONSerialization.data(withJSONObject: replies).write(
      to: home.appendingPathComponent("replies.json"), options: .atomic)
  }

  func calls() -> [[String: Any]] {
    guard let data = try? Data(contentsOf: home.appendingPathComponent("calls.json")),
      let value = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return [] }
    return value
  }

  var actions: [String] { calls().compactMap { $0["action"] as? String } }

  func waitFor(_ condition: () -> Bool, timeout: TimeInterval = 5) async throws {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() && Date() < deadline { try await Task.sleep(for: .milliseconds(10)) }
    guard condition() else {
      XCTFail("Synthetic app operation did not finish within its deadline")
      throw CocoaError(.fileReadUnknown)
    }
  }

  func loadManaged(paired: Bool = false) throws {
    model.installation = try JSONDecoder().decode(
      Installation.self,
      from: JSONSerialization.data(withJSONObject: Self.state(mode: "managed", paired: paired)))
    model.hasLoaded = true
  }

  func close() {
    model.stopConnector()
    onOpenDocker = nil
    try? FileManager.default.removeItem(at: root)
  }

  static func state(mode: String = "existing", ready: Bool = true, paired: Bool = false) -> [String:
    Any]
  {
    [
      "mode": mode, "configured": true, "initialized": mode == "managed", "ready": ready,
      "paired": paired, "can_manage_services": mode == "managed",
      "dashboard": mode == "managed" ? "http://127.0.0.1:9493" : "http://127.0.0.1:19473",
      "health": ready ? "healthy" : "offline", "server_count": 1, "connectors": [],
      "services": mode == "managed"
        ? ["openmaskit", "presidio-analyzer", "connector-relay"].map {
          ["name": $0, "state": ready ? "running" : "exited", "health": ready ? "healthy" : ""]
        } : [],
    ]
  }

  static func requirements(missing: String? = nil) -> [String: Any] {
    [
      "ready": missing == nil,
      "checks": ["desktop", "cli", "context", "compose", "daemon"].map {
        [
          "id": $0, "title": $0 == "desktop" ? "Docker Desktop" : $0,
          "state": $0 == missing ? "needs_attention" : "ready",
          "detail": $0 == missing
            ? "Install or open Docker Desktop, then check again." : "Available",
        ]
      },
    ]
  }

  private static let script = #"""
    #!/usr/bin/env python3
    import fcntl, json, pathlib, sys, time
    args = sys.argv[1:]
    assert args[0] == '--home'
    home = pathlib.Path(args[1])
    action = args[2]
    incoming = sys.stdin.read() if action == 'pair' else ''
    with (home / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        reply = json.loads((home / 'replies.json').read_text()).get(action, {'body': {'ready': True}})
        log = home / 'calls.json'
        calls = json.loads(log.read_text()) if log.exists() else []
        calls.append({'action': action, 'arguments': args[3:], 'input': incoming})
        log.write_text(json.dumps(calls))
    if action == 'connect':
        while home.exists(): time.sleep(.05)
        sys.exit(0)
    if reply.get('wait'):
        deadline = time.monotonic() + 10
        while not (home / reply['wait']).exists() and time.monotonic() < deadline: time.sleep(.01)
    if 'raw' in reply: sys.stdout.write(reply['raw'])
    else: print(json.dumps(reply.get('body', {})))
    if 'error' in reply: sys.stderr.write(json.dumps(reply['error']))
    sys.exit(reply.get('exit', 0))
    """#
}
