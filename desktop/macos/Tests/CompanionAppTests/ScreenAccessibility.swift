import AppKit

/// SwiftUI's virtual accessibility nodes can implement the public selectors without
/// formally conforming to the complete NSAccessibilityProtocol. Keep those nodes.
@MainActor struct ScreenAccessibility {
  let object: NSObject

  private func attribute(_ getter: String, legacy: NSAccessibility.Attribute) -> Any? {
    if object.responds(to: NSSelectorFromString(getter)) {
      return object.value(forKey: getter)
    }
    let names = NSSelectorFromString("accessibilityAttributeNames")
    let value = NSSelectorFromString("accessibilityAttributeValue:")
    guard object.responds(to: names), object.responds(to: value),
      let supported = object.perform(names)?.takeUnretainedValue() as? [String],
      supported.contains(legacy.rawValue)
    else { return nil }
    return object.perform(value, with: legacy.rawValue)?.takeUnretainedValue()
  }

  func accessibilityChildren() -> [Any]? {
    attribute("accessibilityChildren", legacy: .children) as? [Any]
  }
  func accessibilityLabel() -> String? {
    attribute("accessibilityLabel", legacy: .description) as? String
  }
  func accessibilityTitle() -> String? {
    attribute("accessibilityTitle", legacy: .title) as? String
  }
  func accessibilityValue() -> Any? { attribute("accessibilityValue", legacy: .value) }
  func accessibilityIdentifier() -> String? {
    attribute("accessibilityIdentifier", legacy: .identifier) as? String
  }
  func accessibilityRole() -> NSAccessibility.Role? {
    guard let value = attribute("accessibilityRole", legacy: .role) as? String else { return nil }
    return NSAccessibility.Role(rawValue: value)
  }
  func isAccessibilityEnabled() -> Bool {
    if object.responds(to: NSSelectorFromString("isAccessibilityEnabled")) {
      return object.value(forKey: "accessibilityEnabled") as? Bool ?? false
    }
    return attribute("accessibilityEnabled", legacy: .enabled) as? Bool ?? false
  }
  func accessibilityPerformPress() -> Bool {
    let selector = NSSelectorFromString("accessibilityPerformPress")
    guard object.responds(to: selector) else { return false }
    return object.value(forKey: "accessibilityPerformPress") as? Bool ?? false
  }
  func setAccessibilityValue(_ value: String) {
    if object.responds(to: NSSelectorFromString("setAccessibilityValue:")) {
      object.setValue(value, forKey: "accessibilityValue")
    }
  }
}
