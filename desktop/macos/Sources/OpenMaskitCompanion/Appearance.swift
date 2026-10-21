import AppKit
import SwiftUI

/// Shared with OpenMaskit's dark web palette. Keep a future light theme coordinated.
enum CompanionTheme {
  static let root = color(0x0a0c10)
  static let surface = color(0x12151c)
  static let elevated = color(0x181c25)
  static let border = color(0x262d3a)
  static let text = color(0xe8ecf0)
  static let secondary = color(0x94a0b3)
  static let muted = color(0x6b7589)
  static let accent = color(0x58a6ff)
  static let teal = color(0x2dd4bf)
  static let green = color(0x34d399)
  static let red = color(0xf87171)
  static let orange = color(0xfb923c)

  private static func color(_ hex: UInt32) -> Color {
    Color(
      red: Double((hex >> 16) & 255) / 255,
      green: Double((hex >> 8) & 255) / 255,
      blue: Double(hex & 255) / 255)
  }
}

struct CompanionBrandIcon: View {
  let size: CGFloat

  var body: some View {
    Group {
      if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "png"),
        let image = NSImage(contentsOf: url)
      {
        Image(nsImage: image).resizable().interpolation(.high)
      } else {
        Image(systemName: "link").resizable().scaledToFit()
          .foregroundStyle(CompanionTheme.accent)
      }
    }
    .frame(width: size, height: size)
    .accessibilityHidden(true)
  }
}

struct CompanionPanel<Content: View>: View {
  let title: String
  let detail: String?
  let content: Content

  init(_ title: String, detail: String? = nil, @ViewBuilder content: () -> Content) {
    self.title = title
    self.detail = detail
    self.content = content()
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      HStack(spacing: 8) {
        RoundedRectangle(cornerRadius: 1).fill(CompanionTheme.accent)
          .frame(width: 3, height: 13)
        Text(title).font(.system(size: 13, weight: .semibold, design: .monospaced))
          .accessibilityAddTraits(.isHeader)
        Spacer()
        if let detail {
          Text(detail).font(.system(size: 11)).foregroundStyle(CompanionTheme.secondary)
        }
      }
      content
    }
    .padding(14)
    .frame(maxWidth: .infinity, alignment: .leading)
    .background(CompanionTheme.surface, in: RoundedRectangle(cornerRadius: 10))
    .overlay(RoundedRectangle(cornerRadius: 10).stroke(CompanionTheme.border, lineWidth: 1))
  }
}

struct CompanionBadge: View {
  let title: String
  let color: Color

  var body: some View {
    Text(title).font(.system(size: 10, weight: .medium, design: .monospaced))
      .foregroundStyle(color).padding(.horizontal, 7).padding(.vertical, 4)
      .background(color.opacity(0.10), in: RoundedRectangle(cornerRadius: 4))
      .overlay(RoundedRectangle(cornerRadius: 4).stroke(color.opacity(0.25), lineWidth: 1))
  }
}

struct CompanionButtonStyle: ButtonStyle {
  enum Kind { case primary, secondary, danger }
  var kind: Kind = .secondary
  @Environment(\.isEnabled) private var isEnabled

  func makeBody(configuration: Configuration) -> some View {
    let tint = kind == .danger ? CompanionTheme.red : CompanionTheme.accent
    return configuration.label
      .font(.system(size: 12, weight: .medium))
      .foregroundStyle(kind == .primary ? CompanionTheme.root : tint)
      .padding(.horizontal, 11).padding(.vertical, 7)
      .background(
        kind == .primary ? tint : CompanionTheme.elevated,
        in: RoundedRectangle(cornerRadius: 6)
      )
      .overlay(
        RoundedRectangle(cornerRadius: 6)
          .stroke(kind == .primary ? Color.clear : tint.opacity(0.30), lineWidth: 1)
      )
      .opacity(isEnabled ? (configuration.isPressed ? 0.75 : 1) : 0.42)
  }
}
