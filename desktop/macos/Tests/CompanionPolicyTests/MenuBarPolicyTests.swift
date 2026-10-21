import XCTest

@testable import CompanionPolicy

final class MenuBarPolicyTests: XCTestCase {
  func testAllInitialOptionAndWindowCombinations() {
    for show in [false, true] {
      for close in [false, true] {
        for closed in [false, true] {
          let state = MenuBarState(
            showInMenuBar: show, closeToMenuBar: close,
            mainWindowClosed: closed)
          XCTAssertEqual(
            state.menuBarVisible, show || (close && closed),
            "show=\(show), close=\(close), closed=\(closed)")
        }
      }
    }
  }

  func testClosingAndReopeningWithCloseOptionEnabled() {
    var state = MenuBarState(
      showInMenuBar: false, closeToMenuBar: true,
      mainWindowClosed: false)
    XCTAssertEqual(state.transition(.mainWindowWillClose), [.hideDock])
    XCTAssertTrue(state.mainWindowClosed)
    XCTAssertTrue(state.menuBarVisible)

    XCTAssertEqual(state.transition(.reopenRequested), [.revealMainWindow])
    XCTAssertFalse(state.mainWindowClosed)
    XCTAssertFalse(state.menuBarVisible)
  }

  func testClosingNormallyDoesNotHideDockOrShowMenuBar() {
    var state = MenuBarState(
      showInMenuBar: false, closeToMenuBar: false,
      mainWindowClosed: false)
    XCTAssertEqual(state.transition(.mainWindowWillClose), [])
    XCTAssertTrue(state.mainWindowClosed)
    XCTAssertFalse(state.menuBarVisible)
  }

  func testAlwaysShowDoesNotChangeClosePreferenceOrWindowEffects() {
    var state = MenuBarState(
      showInMenuBar: false, closeToMenuBar: false,
      mainWindowClosed: false)
    XCTAssertEqual(state.transition(.showInMenuBarChanged(true)), [])
    XCTAssertTrue(state.showInMenuBar)
    XCTAssertFalse(state.closeToMenuBar)
    XCTAssertTrue(state.menuBarVisible)

    XCTAssertEqual(state.transition(.mainWindowWillClose), [])
    XCTAssertTrue(state.mainWindowClosed)
    XCTAssertTrue(state.menuBarVisible)
    XCTAssertFalse(state.closeToMenuBar)
  }

  func testDisablingCloseOptionWhileHiddenRequestsOneReopen() {
    var state = MenuBarState(
      showInMenuBar: false, closeToMenuBar: true,
      mainWindowClosed: true)
    XCTAssertEqual(
      state.transition(.closeToMenuBarChanged(false)),
      [.revealMainWindow])
    XCTAssertFalse(state.mainWindowClosed)
    XCTAssertFalse(state.closeToMenuBar)
    XCTAssertFalse(state.menuBarVisible)

    XCTAssertEqual(state.transition(.closeToMenuBarChanged(false)), [])
  }

  func testEnablingCloseOptionWhileHiddenHidesDock() {
    var state = MenuBarState(
      showInMenuBar: false, closeToMenuBar: false,
      mainWindowClosed: true)
    XCTAssertEqual(
      state.transition(.closeToMenuBarChanged(true)),
      [.hideDock])
    XCTAssertTrue(state.mainWindowClosed)
    XCTAssertTrue(state.menuBarVisible)
  }

  func testDuplicateCloseIsNoOpAndExplicitReopenRequestsFocus() {
    var state = MenuBarState(
      showInMenuBar: false, closeToMenuBar: true,
      mainWindowClosed: false)
    XCTAssertEqual(state.transition(.mainWindowWillClose), [.hideDock])
    XCTAssertEqual(state.transition(.mainWindowWillClose), [])
    XCTAssertEqual(state.transition(.reopenRequested), [.revealMainWindow])
    // Each explicit request may need to focus an already-open window.
    XCTAssertEqual(state.transition(.reopenRequested), [.revealMainWindow])
    XCTAssertFalse(state.mainWindowClosed)
  }

  func testChangingAlwaysShowWhileHiddenDoesNotReopenOrChangeCloseOption() {
    var state = MenuBarState(
      showInMenuBar: false, closeToMenuBar: true,
      mainWindowClosed: true)
    XCTAssertEqual(state.transition(.showInMenuBarChanged(true)), [])
    XCTAssertTrue(state.menuBarVisible)
    XCTAssertTrue(state.mainWindowClosed)
    XCTAssertTrue(state.closeToMenuBar)

    XCTAssertEqual(state.transition(.showInMenuBarChanged(false)), [])
    XCTAssertTrue(state.menuBarVisible)
    XCTAssertTrue(state.closeToMenuBar)
  }

  func testExplicitReopenWhileAlreadyOpenRequestsFocus() {
    var state = MenuBarState(
      showInMenuBar: true, closeToMenuBar: false,
      mainWindowClosed: false)
    XCTAssertEqual(state.transition(.reopenRequested), [.revealMainWindow])
    XCTAssertFalse(state.mainWindowClosed)
    XCTAssertTrue(state.menuBarVisible)
  }
}
