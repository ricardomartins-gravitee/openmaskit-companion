import XCTest

@testable import CompanionPolicy

final class MenuBarPolicyTests: XCTestCase {
  func testMenuAlwaysVisibleWithOrWithoutAWindow() {
    for closed in [false, true] {
      XCTAssertTrue(MenuBarState(mainWindowClosed: closed).menuBarVisible)
    }
  }
  func testCloseHidesDockAndReopenKeepsMenuAvailable() {
    var state = MenuBarState()
    XCTAssertEqual(state.transition(.mainWindowWillClose), [.hideDock])
    XCTAssertTrue(state.mainWindowClosed && state.menuBarVisible)
    XCTAssertEqual(state.transition(.mainWindowWillClose), [])
    XCTAssertEqual(state.transition(.reopenRequested), [.revealMainWindow])
    XCTAssertFalse(state.mainWindowClosed)
    XCTAssertTrue(state.menuBarVisible)
    XCTAssertEqual(state.transition(.reopenRequested), [.revealMainWindow])
  }
}
