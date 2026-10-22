import AppKit
import Combine
import CompanionPolicy

/// The menu bar item is permanent. Explicit window events change Dock presence.
@MainActor public final class AppPreferences: ObservableObject {
  @Published public private(set) var state: MenuBarState
  public var openMainWindow: (@MainActor () -> Void)?
  private let defaults: UserDefaults
  private let setActivationPolicy: @MainActor (NSApplication.ActivationPolicy) -> Void
  private let activate: @MainActor () -> Void
  @Published public var automaticallyStartServices: Bool {
    didSet {
      if automaticallyStartServices != oldValue {
        defaults.set(automaticallyStartServices, forKey: "automaticallyStartServices")
      }
    }
  }

  public init(
    defaults: UserDefaults = .standard,
    setActivationPolicy: @escaping @MainActor (NSApplication.ActivationPolicy) -> Void = {
      NSApplication.shared.setActivationPolicy($0)
    },
    activate: @escaping @MainActor () -> Void = {
      NSApplication.shared.activate(ignoringOtherApps: true)
    }
  ) {
    defaults.register(defaults: ["automaticallyStartServices": true])
    self.defaults = defaults
    self.setActivationPolicy = setActivationPolicy
    self.activate = activate
    automaticallyStartServices = defaults.bool(forKey: "automaticallyStartServices")
    state = MenuBarState()
  }

  public var mainWindowClosed: Bool { state.mainWindowClosed }
  public var menuBarVisible: Bool { state.menuBarVisible }

  public func windowClosed() { dispatch(.mainWindowWillClose) }
  public func revealMainWindow() { dispatch(.reopenRequested) }

  public func enterMenuBar() {
    dispatch(.mainWindowWillClose)
    setActivationPolicy(.accessory)
  }

  public func windowPresented() {
    if state.mainWindowClosed {
      var next = state
      next.mainWindowClosed = false
      state = next
    }
    setActivationPolicy(.regular)
    activate()
  }

  private func dispatch(_ event: MenuBarEvent) {
    let previous = state
    var next = state
    let effects = next.transition(event)
    if next != previous { state = next }
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
