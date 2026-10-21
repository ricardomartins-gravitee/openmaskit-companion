import CompanionDesktopCore
import SwiftUI

/// The only main window is first-run onboarding. Configured use stays in the menu bar.
struct CompanionOnboarding: View {
  @ObservedObject var model: CompanionModel
  @ObservedObject var preferences: AppPreferences

  var body: some View {
    VStack(alignment: .leading, spacing: CompanionTokens.spaceLg) {
      HStack(spacing: CompanionTokens.spaceSm) {
        CompanionBrandIcon(size: 36)
        Text("OpenMaskit Companion").font(CompanionTypography.title)
        Spacer()
        CompanionBadge(title: "Development alpha", color: CompanionTheme.orange)
      }
      if model.hasLoaded {
        InstallationSetup(model: model)
      } else {
        ProgressView("Reading your installation settings…")
        if !model.message.isEmpty {
          Button("Retry") { Task { await model.refresh() } }
            .buttonStyle(CompanionButtonStyle())
        }
      }
      InstallationFeedback(model: model)
      HStack {
        Text("Once configured, Companion runs from the menu bar.")
          .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
        Spacer()
        Button("Settings…") { model.showSettings?() }
          .buttonStyle(CompanionButtonStyle())
      }
    }
    .font(CompanionTypography.body).foregroundStyle(CompanionTheme.text)
    .padding(CompanionTokens.spaceLg).frame(width: 620)
    .fixedSize(horizontal: false, vertical: true)
    .background(CompanionTheme.root).tint(CompanionTheme.accent).preferredColorScheme(.dark)
  }
}

struct LocalMCPSettings: View {
  @ObservedObject var model: CompanionModel

  var body: some View {
    CompanionPanel("Local MCPs", detail: "\(model.profiles.count) approved") {
      if model.installation.mode == .existing {
        Text("Manage your existing MCP servers in the OpenMaskit dashboard.")
          .foregroundStyle(CompanionTheme.secondary)
        Button("Open OpenMaskit") { Task { await model.openDashboard() } }
          .buttonStyle(CompanionButtonStyle()).disabled(!model.installation.canOpenDashboard)
      } else {
        Text(
          "Approve programs on this Mac, then add their connections to OpenMaskit. Configure privacy rules in its dashboard."
        )
        .foregroundStyle(CompanionTheme.secondary).fixedSize(horizontal: false, vertical: true)
        Button("Add Local MCP…") { model.approve() }
          .buttonStyle(CompanionButtonStyle(kind: .primary))
          .disabled(!model.installation.paired || !model.installation.ready)
        if model.profiles.isEmpty {
          Text("No local MCP profiles added yet.").foregroundStyle(CompanionTheme.secondary)
        }
        ForEach(model.profiles) { profile in
          HStack {
            Label(profile.name, systemImage: "checkmark.shield")
            Spacer()
            Button("Add to OpenMaskit") {
              Task {
                await model.action(
                  ["register", profile.id, "--name", profile.name],
                  success: "MCP added. Configure its checks in OpenMaskit.")
              }
            }
            .buttonStyle(CompanionButtonStyle())
            .disabled(!model.connectorRunning || !model.installation.canUseLocalConnector)
          }
        }
      }
    }.disabled(model.busy)
  }
}
