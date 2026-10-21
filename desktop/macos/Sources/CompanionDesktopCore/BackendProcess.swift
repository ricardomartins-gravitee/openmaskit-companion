import Darwin
import Foundation

public enum BackendFailure: LocalizedError {
  case launch, timeout, outputLimit
  public var errorDescription: String? {
    switch self {
    case .launch: return "The Companion service helper could not start."
    case .timeout: return "The action timed out. Check service status and try again."
    case .outputLimit: return "The service helper returned too much data. Check service status."
    }
  }
}

private final class BoundedOutput: @unchecked Sendable {
  private let lock = NSLock()
  private var data = Data()
  private var exceeded = false
  private let limit: Int
  init(limit: Int) { self.limit = limit }
  func append(_ chunk: Data) {
    lock.lock()
    defer { lock.unlock() }
    if data.count + chunk.count > limit { exceeded = true }
    data.append(chunk.prefix(max(0, limit - data.count)))
  }
  func result() throws -> Data {
    lock.lock()
    defer { lock.unlock() }
    if exceeded { throw BackendFailure.outputLimit }
    return data
  }
}

public struct BackendResult: Sendable {
  public let status: Int32
  public let output: Data
  public let errors: Data
}

public enum BackendProcess {
  /// Both pipes drain concurrently, with bounded memory and a bounded child lifetime.
  public static func run(
    executable: URL, arguments: [String], input: Data? = nil,
    timeout: TimeInterval = 45, outputLimit: Int = 1_048_576
  ) async throws -> BackendResult {
    guard (input?.count ?? 0) <= 4096 else { throw BackendFailure.outputLimit }
    return try await Task.detached {
      try execute(
        executable: executable, arguments: arguments, input: input, timeout: timeout,
        outputLimit: outputLimit)
    }.value
  }

  private static func execute(
    executable: URL, arguments: [String], input: Data?, timeout: TimeInterval, outputLimit: Int
  ) throws -> BackendResult {
    let process = Process()
    let output = Pipe()
    let errors = Pipe()
    let incoming = Pipe()
    process.executableURL = executable
    process.arguments = arguments
    process.standardOutput = output
    process.standardError = errors
    process.standardInput = incoming
    let completed = DispatchSemaphore(value: 0)
    process.terminationHandler = { _ in completed.signal() }
    do { try process.run() } catch { throw BackendFailure.launch }
    let readers = DispatchGroup()
    let stdout = BoundedOutput(limit: outputLimit)
    let stderr = BoundedOutput(limit: outputLimit)
    for (pipe, buffer) in [(output, stdout), (errors, stderr)] {
      readers.enter()
      DispatchQueue.global().async {
        defer { readers.leave() }
        while let chunk = try? pipe.fileHandleForReading.read(upToCount: 65_536), !chunk.isEmpty {
          buffer.append(chunk)
        }
      }
    }
    if let input { try? incoming.fileHandleForWriting.write(contentsOf: input) }
    try? incoming.fileHandleForWriting.close()
    let timedOut = completed.wait(timeout: .now() + timeout) == .timedOut
    if timedOut && process.isRunning {
      process.terminate()
      if completed.wait(timeout: .now() + 3) == .timedOut && process.isRunning {
        kill(process.processIdentifier, SIGKILL)
        _ = completed.wait(timeout: .now() + 2)
      }
    }
    if readers.wait(timeout: .now() + 2) == .timedOut {
      try? output.fileHandleForReading.close()
      try? errors.fileHandleForReading.close()
    }
    if timedOut { throw BackendFailure.timeout }
    return try BackendResult(
      status: process.terminationStatus, output: stdout.result(), errors: stderr.result())
  }
}
