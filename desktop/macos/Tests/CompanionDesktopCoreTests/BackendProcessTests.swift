import Foundation
import XCTest

@testable import CompanionDesktopCore

final class BackendProcessTests: XCTestCase {
  func testBothPipesDrainWithoutDeadlockingAndInputStaysPrivate() async throws {
    let result = try await BackendProcess.run(
      executable: URL(fileURLWithPath: "/bin/sh"),
      arguments: [
        "-c",
        "i=0; while [ $i -lt 10000 ]; do printf synthetic; printf diagnostic >&2; i=$((i+1)); done",
      ], timeout: 5)
    XCTAssertEqual(result.status, 0)
    XCTAssertEqual(result.output.count, 90000)
    XCTAssertEqual(result.errors.count, 100000)
    let input = Data("synthetic-pairing-code\n".utf8)
    let echoed = try await BackendProcess.run(
      executable: URL(fileURLWithPath: "/bin/cat"), arguments: [], input: input)
    XCTAssertEqual(echoed.output, input)
  }

  func testTimeoutTerminatesOnlyOwnedChildAndDoesNotExposeItsArguments() async {
    do {
      _ = try await BackendProcess.run(
        executable: URL(fileURLWithPath: "/bin/sleep"), arguments: ["5"], timeout: 0.05)
      XCTFail("Expected timeout")
    } catch { XCTAssertTrue(error is BackendFailure) }
  }

  func testOutputAndInputLimitsAreEnforced() async {
    do {
      _ = try await BackendProcess.run(
        executable: URL(fileURLWithPath: "/usr/bin/printf"), arguments: ["%080000d", "1"],
        outputLimit: 64)
      XCTFail("Expected output limit")
    } catch { XCTAssertTrue(error is BackendFailure) }
    do {
      _ = try await BackendProcess.run(
        executable: URL(fileURLWithPath: "/bin/cat"), arguments: [],
        input: Data(repeating: 1, count: 5000))
      XCTFail("Expected input limit")
    } catch { XCTAssertTrue(error is BackendFailure) }
  }
}
