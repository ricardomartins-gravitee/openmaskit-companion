import AppKit
import Combine
import CompanionDesktopCore

@main enum DesktopCoreAcceptance {
  @MainActor static func main() {
    let suite = "companion-acceptance-" + UUID().uuidString
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    for show in [false, true] {
      for close in [false, true] {
        defaults.set(show, forKey: "showInMenuBar")
        defaults.set(close, forKey: "closeToMenuBar")
        var policies: [NSApplication.ActivationPolicy] = []
        var opened = 0
        var activated = 0
        var changes = 0
        let preferences = AppPreferences(
          defaults: defaults,
          setActivationPolicy: { policies.append($0) }, activate: { activated += 1 })
        preferences.openMainWindow = { opened += 1 }
        let observation = preferences.objectWillChange.sink { changes += 1 }
        preferences.enterMenuBar()
        precondition(preferences.menuBarVisible && opened == 0 && policies.last == .accessory)
        let previous = changes
        preferences.windowClosed()
        precondition(changes == previous && opened == 0)
        preferences.revealMainWindow()
        precondition(policies.last == .regular && opened == 1 && activated == 1)
        precondition(preferences.menuBarVisible && !preferences.mainWindowClosed)
        preferences.windowClosed()
        precondition(preferences.menuBarVisible && policies.last == .accessory)
        withExtendedLifetime(observation) {}
      }
    }
    let preferences = AppPreferences(
      defaults: defaults, setActivationPolicy: { _ in }, activate: {})
    precondition(preferences.automaticallyStartServices)
    preferences.automaticallyStartServices = false
    precondition(
      !AppPreferences(defaults: defaults, setActivationPolicy: { _ in }, activate: {})
        .automaticallyStartServices)
    let application = NSApplication.shared
    let original = application.activationPolicy()
    defer { application.setActivationPolicy(original) }
    let live = AppPreferences(defaults: defaults, activate: {})
    live.windowClosed()
    precondition(application.activationPolicy() == .accessory)
    live.revealMainWindow()
    precondition(application.activationPolicy() == .regular)
    precondition(live.menuBarVisible)
    print(
      "PASS: permanent menu, retired preferences ignored, no feedback/reopen loop, close/reopen AppKit presentation and startup persistence"
    )
  }
}
