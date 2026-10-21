import Foundation
import XCTest

@testable import CompanionDesktopCore

final class DesktopInstanceLockTests: XCTestCase {
  func testDuplicateAndNormalRelease() throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: folder) }
    var owner: DesktopInstanceLock? = try DesktopInstanceLock(directory: folder)
    XCTAssertTrue(owner!.isOwner)
    let duplicate = try DesktopInstanceLock(directory: folder)
    XCTAssertFalse(duplicate.isOwner)
    withExtendedLifetime(owner) {}
    owner = nil
    let next = try DesktopInstanceLock(directory: folder)
    XCTAssertTrue(next.isOwner)
    withExtendedLifetime(next) {}
  }

  func testRejectsSymbolicLinkAndPublicLockFile() throws {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(
      at: folder, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    defer { try? FileManager.default.removeItem(at: folder) }
    let destination = folder.appendingPathComponent("unrelated")
    try Data("unchanged".utf8).write(to: destination)
    let file = folder.appendingPathComponent("desktop.lock")
    try FileManager.default.createSymbolicLink(at: file, withDestinationURL: destination)
    XCTAssertThrowsError(try DesktopInstanceLock(directory: folder))
    XCTAssertEqual(try Data(contentsOf: destination), Data("unchanged".utf8))
    try FileManager.default.removeItem(at: file)
    try Data().write(to: file)
    try FileManager.default.setAttributes([.posixPermissions: 0o644], ofItemAtPath: file.path)
    XCTAssertThrowsError(try DesktopInstanceLock(directory: folder))
  }
}
