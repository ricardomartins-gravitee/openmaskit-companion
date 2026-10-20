// Standalone fallback for Macs with Command Line Tools but no XCTest framework.
@main enum MenuBarAcceptance {
    static func main() {
        for show in [false, true] {
            for close in [false, true] {
                for hidden in [false, true] {
                    let expected = show || (close && hidden)
                    precondition(MenuBarPolicy.isVisible(alwaysShow: show, closeToMenuBar: close,
                                                        mainWindowClosed: hidden) == expected)
                }
            }
        }
        print("PASS: all eight menu bar visibility combinations")
    }
}
