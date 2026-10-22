import AppKit
import CompanionDesktopCore

@MainActor enum CompanionInstance {
  static let identifier = "io.github.ricardomartins-gravitee.openmaskit-companion"
  static let reopenNotification = Notification.Name(identifier + ".reopen")
  private static var lock: DesktopInstanceLock?

  /// Runs before any scene, service monitor or connector is started. The fixed
  /// per-user location covers copies in different folders and direct launches.
  static func enforce() {
    do {
      let directory = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/OpenMaskit Companion/Runtime")
      lock = try DesktopInstanceLock(directory: directory)
      let peers = NSWorkspace.shared.runningApplications.filter {
        $0.processIdentifier != ProcessInfo.processInfo.processIdentifier
          && ($0.bundleIdentifier == identifier
            || $0.bundleIdentifier?.hasPrefix(identifier + ".") == true)
      }
      // The peer check also handles an older installed build without a lock.
      if lock?.isOwner != true || peers.contains(where: { $0.isFinishedLaunching }) {
        if let peer = peers.first(where: { $0.isFinishedLaunching }) ?? peers.first {
          DistributedNotificationCenter.default().postNotificationName(
            reopenNotification, object: String(peer.processIdentifier), userInfo: nil,
            deliverImmediately: true)
          peer.activate(options: [.activateAllWindows])
        }
        exit(EXIT_SUCCESS)
      }
    } catch {
      let alert = NSAlert()
      alert.messageText = "Companion could not start safely"
      alert.informativeText =
        "Its single-app lock is unavailable. Check your account's application support folder and try again."
      alert.runModal()
      exit(EXIT_FAILURE)
    }
  }
}
