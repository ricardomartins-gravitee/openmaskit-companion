// Standalone fallback for Macs with Command Line Tools but no XCTest framework.
@main enum MenuBarAcceptance {
    static func main() {
        checkInitialVisibilityCombinations()
        checkCloseAndExplicitReopen()
        checkCloseOptionChangeWhileHidden()
        checkPreferenceIndependence()
        checkDuplicateLifecycleEvents()
        print("PASS: menu bar visibility and lifecycle policy")
    }

    private static func checkInitialVisibilityCombinations() {
        for show in [false, true] {
            for close in [false, true] {
                for closed in [false, true] {
                    let state = MenuBarState(showInMenuBar: show, closeToMenuBar: close,
                                             mainWindowClosed: closed)
                    precondition(state.menuBarVisible == (show || (close && closed)))
                }
            }
        }
    }

    private static func checkCloseAndExplicitReopen() {
        var state = MenuBarState(showInMenuBar: false, closeToMenuBar: true)
        precondition(state.transition(.mainWindowWillClose) == [.hideDock])
        precondition(state.mainWindowClosed && state.menuBarVisible)
        precondition(state.transition(.reopenRequested) == [.revealMainWindow])
        precondition(!state.mainWindowClosed && !state.menuBarVisible)

        var ordinary = MenuBarState()
        precondition(ordinary.transition(.mainWindowWillClose).isEmpty)
        precondition(ordinary.mainWindowClosed && !ordinary.menuBarVisible)
    }

    private static func checkCloseOptionChangeWhileHidden() {
        var state = MenuBarState(mainWindowClosed: true)
        precondition(state.transition(.closeToMenuBarChanged(true)) == [.hideDock])
        precondition(state.mainWindowClosed && state.menuBarVisible)
        precondition(state.transition(.closeToMenuBarChanged(false)) == [.revealMainWindow])
        precondition(!state.mainWindowClosed && !state.menuBarVisible)
    }

    private static func checkPreferenceIndependence() {
        var state = MenuBarState(closeToMenuBar: false, mainWindowClosed: true)
        precondition(state.transition(.showInMenuBarChanged(true)).isEmpty)
        precondition(state.showInMenuBar && !state.closeToMenuBar && state.menuBarVisible)
        precondition(state.transition(.showInMenuBarChanged(false)).isEmpty)
        precondition(!state.showInMenuBar && !state.closeToMenuBar && !state.menuBarVisible)
    }

    private static func checkDuplicateLifecycleEvents() {
        var state = MenuBarState(closeToMenuBar: true)
        precondition(state.transition(.mainWindowWillClose) == [.hideDock])
        precondition(state.transition(.mainWindowWillClose).isEmpty)
        precondition(state.transition(.reopenRequested) == [.revealMainWindow])
        precondition(state.transition(.reopenRequested) == [.revealMainWindow])
        precondition(!state.mainWindowClosed)
    }
}
