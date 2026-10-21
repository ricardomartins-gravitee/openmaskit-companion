import CompanionDesktopCore
import Darwin
import Foundation

@main enum InstanceAcceptance {
  static func main() throws {
    let args = CommandLine.arguments
    if args.count == 3 {
      let lock = try DesktopInstanceLock(directory: URL(fileURLWithPath: args[2]))
      if args[1] == "--hold" {
        precondition(lock.isOwner)
        FileHandle.standardOutput.write(Data("Y".utf8))
        _ = try FileHandle.standardInput.read(upToCount: 1)
      } else {
        print(lock.isOwner ? "owner" : "busy")
      }
      withExtendedLifetime(lock) {}
      return
    }
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: root) }
    let directory = root.appendingPathComponent("instance")
    func claim() throws -> String {
      let child = Process()
      let output = Pipe()
      child.executableURL = URL(fileURLWithPath: args[0])
      child.arguments = ["--claim", directory.path]
      child.standardOutput = output
      try child.run()
      let result = output.fileHandleForReading.readDataToEndOfFile()
      child.waitUntilExit()
      precondition(child.terminationStatus == 0)
      return String(decoding: result, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
    }
    var primary: DesktopInstanceLock? = try DesktopInstanceLock(directory: directory)
    precondition(primary!.isOwner)
    var result = try claim()
    precondition(result == "busy", "Second process must not acquire the lock")
    let second = try DesktopInstanceLock(directory: directory)
    precondition(!second.isOwner, "A second object cannot become an owner")
    withExtendedLifetime(primary) {}
    primary = nil
    result = try claim()
    precondition(result == "owner", "Normal exit must release ownership")

    let crashed = Process()
    let ready = Pipe()
    let input = Pipe()
    crashed.executableURL = URL(fileURLWithPath: args[0])
    crashed.arguments = ["--hold", directory.path]
    crashed.standardOutput = ready
    crashed.standardInput = input
    try crashed.run()
    let signal = try ready.fileHandleForReading.read(upToCount: 1)
    precondition(signal == Data("Y".utf8))
    result = try claim()
    precondition(result == "busy")
    kill(crashed.processIdentifier, SIGKILL)
    crashed.waitUntilExit()
    result = try claim()
    precondition(result == "owner", "A crash must not leave stale ownership")
    precondition(
      FileManager.default.fileExists(atPath: directory.appendingPathComponent("desktop.lock").path))

    let unsafe = root.appendingPathComponent("unsafe")
    try FileManager.default.createDirectory(at: unsafe, withIntermediateDirectories: true)
    try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: unsafe.path)
    do {
      _ = try DesktopInstanceLock(directory: unsafe)
      preconditionFailure("An unprotected lock directory must be rejected")
    } catch DesktopInstanceLock.LockError.unavailable {}
    let linked = root.appendingPathComponent("linked")
    try FileManager.default.createSymbolicLink(at: linked, withDestinationURL: directory)
    do {
      _ = try DesktopInstanceLock(directory: linked)
      preconditionFailure("Symlinked lock directories must be rejected")
    } catch DesktopInstanceLock.LockError.unavailable {}
    print(
      "PASS: one owner across processes and copies, normal/crash recovery, private lock and symlink rejection"
    )
  }
}
