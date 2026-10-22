import AppKit
import OpenMaskitDesign
import SwiftUI

// All shared visual values/components come from the revision-pinned design package.
typealias CompanionTheme = OpenMaskitTheme
typealias CompanionTokens = OpenMaskitTokens
typealias CompanionTypography = OpenMaskitTypography
typealias CompanionPanel<Content: View> = OpenMaskitPanel<Content>
typealias CompanionBadge = OpenMaskitBadge
typealias CompanionButtonStyle = OpenMaskitButtonStyle

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
