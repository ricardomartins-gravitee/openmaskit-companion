@main enum MenuBarAcceptance {
  static func main() {
    for closed in [false, true] {
      precondition(MenuBarState(mainWindowClosed: closed).menuBarVisible)
    }
    var state = MenuBarState()
    precondition(state.transition(.mainWindowWillClose) == [.hideDock])
    precondition(state.menuBarVisible && state.mainWindowClosed)
    precondition(state.transition(.mainWindowWillClose).isEmpty)
    precondition(state.transition(.reopenRequested) == [.revealMainWindow])
    precondition(state.menuBarVisible && !state.mainWindowClosed)
    precondition(state.transition(.reopenRequested) == [.revealMainWindow])
    print("PASS: permanent menu availability, close hides Dock, reopen focuses Settings")
  }
}
