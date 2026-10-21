import AppKit
import Combine
import CompanionDesktopCore

@main enum DesktopCoreAcceptance {
    @MainActor static func main() {
        let suite = "companion-acceptance-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let firstLaunch = AppPreferences(defaults: defaults,
            setActivationPolicy: { _ in }, activate: {})
        precondition(firstLaunch.showInMenuBar && firstLaunch.menuBarVisible && !firstLaunch.closeToMenuBar)
        firstLaunch.showInMenuBar = false
        var policies: [NSApplication.ActivationPolicy] = []
        var opened = 0, activated = 0, changes = 0
        let preferences = AppPreferences(defaults: defaults,
            setActivationPolicy: { policies.append($0) }, activate: { activated += 1 })
        preferences.openMainWindow = { opened += 1 }
        let observation = preferences.objectWillChange.sink { changes += 1 }
        preferences.showInMenuBar = false
        preferences.closeToMenuBar = false
        precondition(changes == 0, "Framework echoes must not publish")
        preferences.closeToMenuBar = true
        preferences.windowClosed()
        precondition(policies == [.accessory] && opened == 0)
        precondition(preferences.mainWindowClosed && preferences.menuBarVisible && !preferences.showInMenuBar)
        let beforeEcho = changes
        preferences.synchronizeMenuBarInsertion(true)
        preferences.synchronizeMenuBarInsertion(false)
        precondition(changes == beforeEcho && !preferences.showInMenuBar, "Insertion synchronization must not publish")
        preferences.windowClosed()
        precondition(policies == [.accessory], "Duplicate close must not reopen or repeat effects")
        preferences.revealMainWindow()
        precondition(policies == [.accessory, .regular] && opened == 1 && activated == 1)
        precondition(!preferences.mainWindowClosed && !preferences.menuBarVisible)
        preferences.windowClosed()
        preferences.closeToMenuBar = false
        precondition(opened == 2 && policies.last == .regular)
        let relaunched = AppPreferences(defaults: defaults, setActivationPolicy: { _ in }, activate: {})
        precondition(!relaunched.closeToMenuBar && !relaunched.showInMenuBar && !relaunched.mainWindowClosed)
        withExtendedLifetime(observation) {}

        let application = NSApplication.shared
        let original = application.activationPolicy()
        defer { application.setActivationPolicy(original) }
        let live = AppPreferences(defaults: defaults, activate: {})
        live.closeToMenuBar = true
        live.windowClosed()
        precondition(application.activationPolicy() == .accessory, "AppKit did not hide Dock presence")
        live.revealMainWindow()
        precondition(application.activationPolicy() == .regular, "AppKit did not restore Dock presence")
        print("PASS: preferences, no publication loop, close/reopen effects, persistence and actual AppKit activation")
    }
}
