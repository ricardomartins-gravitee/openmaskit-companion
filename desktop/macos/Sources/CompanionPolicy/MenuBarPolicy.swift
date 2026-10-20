public enum MenuBarPolicy {
    public static func isVisible(alwaysShow: Bool, closeToMenuBar: Bool, mainWindowClosed: Bool) -> Bool {
        alwaysShow || (closeToMenuBar && mainWindowClosed)
    }
}
