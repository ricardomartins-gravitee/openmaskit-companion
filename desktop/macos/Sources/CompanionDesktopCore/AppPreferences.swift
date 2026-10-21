import AppKit
import Combine
import CompanionPolicy

/// Only explicit user/window events change presentation. SwiftUI appearance and
/// MenuBarExtra synchronization callbacks must not publish preference changes.
@MainActor public final class AppPreferences: ObservableObject {
  @Published public private(set) var state: MenuBarState
  public var openMainWindow: (@MainActor () -> Void)?
  private let defaults: UserDefaults
  private let setActivationPolicy: @MainActor (NSApplication.ActivationPolicy) -> Void
  private let activate: @MainActor () -> Void

  public init(
    defaults: UserDefaults = .standard,
    setActivationPolicy: @escaping @MainActor (NSApplication.ActivationPolicy) -> Void = {
      NSApplication.shared.setActivationPolicy($0)
    },
    activate: @escaping @MainActor () -> Void = {
      NSApplication.shared.activate(ignoringOtherApps: true)
    }
  ) {
    defaults.register(defaults: ["showInMenuBar": true])
    self.defaults = defaults
    self.setActivationPolicy = setActivationPolicy
    self.activate = activate
    state = MenuBarState(
      showInMenuBar: defaults.bool(forKey: "showInMenuBar"),
      closeToMenuBar: defaults.bool(forKey: "closeToMenuBar"))
  }

  public var showInMenuBar: Bool {
    get { state.showInMenuBar }
    set { dispatch(.showInMenuBarChanged(newValue)) }
  }
  public var closeToMenuBar: Bool {
    get { state.closeToMenuBar }
    set { dispatch(.closeToMenuBarChanged(newValue)) }
  }
  public var mainWindowClosed: Bool { state.mainWindowClosed }
  public var menuBarVisible: Bool { state.menuBarVisible }

  public func windowClosed() { dispatch(.mainWindowWillClose) }
  public func revealMainWindow() { dispatch(.reopenRequested) }

  /// Framework insertion notifications are observations, not user preferences.
  /// In particular, close-only visibility must never enable always-show.
  public func synchronizeMenuBarInsertion(_ inserted: Bool) {}

  private func dispatch(_ event: MenuBarEvent) {
    let previous = state
    var next = state
    let effects = next.transition(event)
    if next != previous { state = next }
    if next.showInMenuBar != previous.showInMenuBar {
      defaults.set(next.showInMenuBar, forKey: "showInMenuBar")
    }
    if next.closeToMenuBar != previous.closeToMenuBar {
      defaults.set(next.closeToMenuBar, forKey: "closeToMenuBar")
    }
    for effect in effects {
      switch effect {
      case .hideDock:
        setActivationPolicy(.accessory)
      case .revealMainWindow:
        setActivationPolicy(.regular)
        openMainWindow?()
        activate()
      }
    }
  }
}
