public enum MenuBarPolicy {
    public static func isVisible(alwaysShow: Bool, closeToMenuBar: Bool, mainWindowClosed: Bool) -> Bool {
        alwaysShow || (closeToMenuBar && mainWindowClosed)
    }
}

public struct MenuBarState: Equatable {
    public var showInMenuBar: Bool
    public var closeToMenuBar: Bool
    public var mainWindowClosed: Bool

    public init(showInMenuBar: Bool = false, closeToMenuBar: Bool = false,
                mainWindowClosed: Bool = false) {
        self.showInMenuBar = showInMenuBar
        self.closeToMenuBar = closeToMenuBar
        self.mainWindowClosed = mainWindowClosed
    }

    public var menuBarVisible: Bool {
        MenuBarPolicy.isVisible(alwaysShow: showInMenuBar, closeToMenuBar: closeToMenuBar,
                                mainWindowClosed: mainWindowClosed)
    }

    @discardableResult
    public mutating func transition(_ event: MenuBarEvent) -> [MenuBarEffect] {
        switch event {
        case .mainWindowWillClose:
            guard !mainWindowClosed else { return [] }
            mainWindowClosed = true
            return closeToMenuBar ? [.hideDock] : []

        case .reopenRequested:
            mainWindowClosed = false
            // Explicit Show/Dock requests must also focus an already-open window.
            return [.revealMainWindow]

        case let .showInMenuBarChanged(value):
            guard showInMenuBar != value else { return [] }
            showInMenuBar = value
            return []

        case let .closeToMenuBarChanged(value):
            guard closeToMenuBar != value else { return [] }
            closeToMenuBar = value
            if value && mainWindowClosed { return [.hideDock] }
            if !value && mainWindowClosed {
                mainWindowClosed = false
                return [.revealMainWindow]
            }
            return []
        }
    }
}

public enum MenuBarEvent: Equatable {
    case mainWindowWillClose
    case reopenRequested
    case showInMenuBarChanged(Bool)
    case closeToMenuBarChanged(Bool)
}

public enum MenuBarEffect: Equatable {
    case hideDock
    case revealMainWindow
}
