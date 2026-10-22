import AppKit
import CompanionDesktopCore
import SwiftUI

@MainActor final class CompanionWindow: NSWindowController, NSWindowDelegate {
  private let preferences: AppPreferences
  private var sizeObservation: NSKeyValueObservation?

  init(title: String, content: AnyView, preferences: AppPreferences) {
    self.preferences = preferences
    let hosting = NSHostingController(rootView: content)
    hosting.sizingOptions = [.preferredContentSize]
    let window = NSWindow(contentViewController: hosting)
    window.title = title
    window.styleMask = [.titled, .closable, .miniaturizable]
    window.isReleasedWhenClosed = false
    window.titlebarAppearsTransparent = true
    window.backgroundColor = NSColor(CompanionTheme.root)
    super.init(window: window)
    window.delegate = self
    sizeObservation = hosting.observe(\.preferredContentSize, options: [.new]) {
      [weak window] host, _ in
      let size = host.preferredContentSize
      DispatchQueue.main.async {
        guard let window, size.width > 0 && size.height > 0 else { return }
        if abs(window.contentLayoutRect.height - size.height) > 0.5 {
          window.setContentSize(size)
        }
      }
    }
    window.setContentSize(NSSize(width: 620, height: 450))
    window.center()
  }

  required init?(coder: NSCoder) { fatalError("Not supported") }

  func present() {
    preferences.windowPresented()
    showWindow(nil)
    window?.makeKeyAndOrderFront(nil)
  }

  func windowWillClose(_ notification: Notification) {
    let anotherWindow = NSApp.windows.contains {
      $0 !== window && $0.isVisible && $0.windowController is CompanionWindow
    }
    if !anotherWindow { preferences.windowClosed() }
  }
}

@MainActor enum CompanionRuntime {
  static let model = CompanionModel()
  static let preferences = AppPreferences()
}
