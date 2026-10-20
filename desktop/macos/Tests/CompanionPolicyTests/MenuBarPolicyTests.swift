import XCTest
@testable import CompanionPolicy

final class MenuBarPolicyTests: XCTestCase {
    func testDefaultsDoNotCreateMenuBarItem() {
        XCTAssertFalse(MenuBarPolicy.isVisible(alwaysShow: false, closeToMenuBar: false, mainWindowClosed: false))
    }
    func testAlwaysShowIsIndependentOfWindowState() {
        for closed in [false, true] {
            XCTAssertTrue(MenuBarPolicy.isVisible(alwaysShow: true, closeToMenuBar: false, mainWindowClosed: closed))
        }
    }
    func testCloseOptionCreatesItemOnlyAfterClose() {
        XCTAssertFalse(MenuBarPolicy.isVisible(alwaysShow: false, closeToMenuBar: true, mainWindowClosed: false))
        XCTAssertTrue(MenuBarPolicy.isVisible(alwaysShow: false, closeToMenuBar: true, mainWindowClosed: true))
    }
    func testClosingNormallyDoesNotCreateMenuBarItem() {
        XCTAssertFalse(MenuBarPolicy.isVisible(alwaysShow: false, closeToMenuBar: false, mainWindowClosed: true))
    }
    func testBothOptionsKeepItemVisibleOnReopen() {
        XCTAssertTrue(MenuBarPolicy.isVisible(alwaysShow: true, closeToMenuBar: true, mainWindowClosed: false))
    }
}
