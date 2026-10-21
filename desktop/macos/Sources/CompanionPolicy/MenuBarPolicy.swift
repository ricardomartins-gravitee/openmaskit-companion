/// Companion is always reachable from its menu bar item. Window presentation
/// only changes Dock presence; it never changes menu availability.
public struct MenuBarState: Equatable {
  public var mainWindowClosed: Bool
  public init(mainWindowClosed: Bool = false) { self.mainWindowClosed = mainWindowClosed }
  public var menuBarVisible: Bool { true }

  @discardableResult
  public mutating func transition(_ event: MenuBarEvent) -> [MenuBarEffect] {
    switch event {
    case .mainWindowWillClose:
      guard !mainWindowClosed else { return [] }
      mainWindowClosed = true
      return [.hideDock]
    case .reopenRequested:
      mainWindowClosed = false
      return [.revealMainWindow]
    }
  }
}

public enum MenuBarEvent: Equatable {
  case mainWindowWillClose
  case reopenRequested
}

public enum MenuBarEffect: Equatable {
  case hideDock
  case revealMainWindow
}
