import AppKit

/// SwiftUI's virtual accessibility nodes can implement the public selectors without
/// formally conforming to the complete NSAccessibilityProtocol. Keep those nodes.
@MainActor struct ScreenAccessibility {
  let object: NSObject

  private func attribute(_ getter: String, legacy: NSAccessibility.Attribute) -> Any? {
    let names = NSSelectorFromString("accessibilityAttributeNames")
    let value = NSSelectorFromString("accessibilityAttributeValue:")
    if object.responds(to: names), object.responds(to: value),
      let supported = object.perform(names)?.takeUnretainedValue() as? [String],
      supported.contains(legacy.rawValue),
      let result = object.perform(value, with: legacy.rawValue)?.takeUnretainedValue()
    {
      return result
    }
    guard object.responds(to: NSSelectorFromString(getter)) else { return nil }
    return object.value(forKey: getter)
  }

  func accessibilityChildren() -> [Any]? {
    var children = attribute("accessibilityChildren", legacy: .children) as? [Any] ?? []
    let navigation = NSSelectorFromString("accessibilityChildrenInNavigationOrder")
    if object.responds(to: navigation),
      let ordered = object.value(forKey: "accessibilityChildrenInNavigationOrder") as? [Any]
    {
      children.append(contentsOf: ordered)
    }
    // Scroll areas expose their primary elements as AXContents as well as children.
    children.append(
      contentsOf: attribute("accessibilityContents", legacy: .contents) as? [Any] ?? [])
    children.append(
      contentsOf: attribute("accessibilityVisibleChildren", legacy: .visibleChildren) as? [Any]
        ?? [])
    return children
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
  var supportsPress: Bool {
    object.responds(to: NSSelectorFromString("accessibilityPerformPress"))
  }
  func setAccessibilityValue(_ value: String) {
    if object.responds(to: NSSelectorFromString("setAccessibilityValue:")) {
      object.setValue(value, forKey: "accessibilityValue")
    }
  }

  var diagnostic: String {
    let fields = [
      "accessibilityLabel", "accessibilityTitle", "accessibilityValue",
      "accessibilityIdentifier", "accessibilityRole",
    ]
    let values = fields.map { field in
      let value =
        object.responds(to: NSSelectorFromString(field))
        ? String(describing: object.value(forKey: field)) : "unsupported"
      return field + "=" + value
    }
    return String(describing: type(of: object)) + " " + values.joined(separator: " | ")
  }
}
