import Darwin
import Foundation

/// A kernel-owned lock survives neither a crash nor process exit. The file stays
/// in place so another launch can never lock a different inode at the same path.
public final class DesktopInstanceLock {
  private let descriptor: Int32
  public let isOwner: Bool

  public init(directory: URL) throws {
    try FileManager.default.createDirectory(
      at: directory, withIntermediateDirectories: true,
      attributes: [.posixPermissions: 0o700])
    var info = stat()
    guard lstat(directory.path, &info) == 0, info.st_uid == getuid(),
      info.st_mode & S_IFMT == S_IFDIR, info.st_mode & 0o077 == 0
    else { throw LockError.unavailable }
    descriptor = open(
      directory.appendingPathComponent("desktop.lock").path,
      O_CREAT | O_RDWR | O_NOFOLLOW | O_CLOEXEC, 0o600)
    guard descriptor >= 0 else { throw LockError.unavailable }
    guard fstat(descriptor, &info) == 0, info.st_uid == getuid(),
      info.st_mode & S_IFMT == S_IFREG, info.st_mode & 0o077 == 0
    else {
      close(descriptor)
      throw LockError.unavailable
    }
    if flock(descriptor, LOCK_EX | LOCK_NB) == 0 {
      isOwner = true
    } else if errno == EWOULDBLOCK {
      isOwner = false
    } else {
      close(descriptor)
      throw LockError.unavailable
    }
  }

  deinit { close(descriptor) }

  public enum LockError: Error { case unavailable }
}
