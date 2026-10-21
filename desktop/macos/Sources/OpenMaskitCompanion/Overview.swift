import AppKit
import CompanionDesktopCore
import SwiftUI

private struct ContentHeight: PreferenceKey {
  static var defaultValue: CGFloat = 0
  static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
    value = max(value, nextValue())
  }
}

struct CompanionOverview: View {
  @ObservedObject var model: CompanionModel
  @ObservedObject var preferences: AppPreferences
  @State private var contentHeight: CGFloat = 272

  private var maximumContentHeight: CGFloat {
    min(620, max(240, (NSScreen.main?.visibleFrame.height ?? 800) - 180))
  }

  var body: some View {
    VStack(spacing: 0) {
      header
      Divider().overlay(CompanionTheme.border)
      ScrollView {
        VStack(spacing: CompanionTokens.spaceMd) {
          if !model.hasLoaded {
            CompanionPanel("Connecting") {
              ProgressView("Reading your installation settings…")
              if !model.message.isEmpty {
                Button("Retry") { Task { await model.refresh() } }
                  .buttonStyle(CompanionButtonStyle(kind: .primary))
              }
            }
          } else if model.installation.needsOnboarding {
            InstallationSetup(model: model)
          } else {
            connection
            localMCPs
          }
          if let error = model.installation.error ?? model.installation.connectionError {
            notice(error, color: CompanionTheme.orange)
          }
          InstallationFeedback(model: model)
        }
        .padding(CompanionTokens.spaceLg)
        .frame(maxWidth: .infinity)
        .background(
          GeometryReader { geometry in
            Color.clear.preference(key: ContentHeight.self, value: geometry.size.height)
          }
        )
      }
      .frame(height: min(contentHeight, maximumContentHeight))
      .onPreferenceChange(ContentHeight.self) { height in
        if height > 0 && abs(contentHeight - height) > 0.5 { contentHeight = height }
      }
      Divider().overlay(CompanionTheme.border)
      footer
    }
    .font(CompanionTypography.body)
    .foregroundStyle(CompanionTheme.text)
    .background(CompanionTheme.root)
    .frame(width: 620)
    .fixedSize(horizontal: false, vertical: true)
    .tint(CompanionTheme.accent)
    .preferredColorScheme(.dark)
    .background(MainWindowObserver(preferences: preferences))
  }

  private var header: some View {
    HStack(spacing: 10) {
      CompanionBrandIcon(size: 36)
      VStack(alignment: .leading, spacing: 3) {
        Text("OpenMaskit Companion")
          .font(CompanionTypography.title)
          .accessibilityAddTraits(.isHeader)
        Text("Local services & MCP connections")
          .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
      }
      Spacer()
      CompanionBadge(title: "Development alpha", color: CompanionTheme.orange)
    }
    .padding(.horizontal, CompanionTokens.spaceLg).padding(.vertical, CompanionTokens.spaceMd)
    .background(CompanionTheme.surface)
  }

  private var connection: some View {
    CompanionPanel(
      "OpenMaskit",
      detail: model.installation.mode == .existing
        ? "Existing installation" : "Companion installation"
    ) {
      HStack(spacing: CompanionTokens.spaceSm) {
        Circle().fill(model.installation.ready ? CompanionTheme.green : CompanionTheme.orange)
          .frame(width: 6, height: 6)
        Text(model.installation.title)
        Spacer()
        Button("Open OpenMaskit") { Task { await model.openDashboard() } }
          .buttonStyle(CompanionButtonStyle(kind: .primary))
          .disabled(!model.installation.canOpenDashboard || model.busy)
      }
      if let address = model.installation.dashboard {
        Text(address).font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
          .textSelection(.enabled)
      }
      if !model.installation.ready {
        Text(
          model.installation.mode == .existing
            ? "Start this installation using its existing controls, or update its address in Settings."
            : "Manage services in Settings → Installation."
        )
        .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
        .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  @ViewBuilder private var localMCPs: some View {
    if model.installation.mode == .existing {
      CompanionPanel("MCP servers", detail: "\(model.installation.serverCount) configured") {
        Text(
          "Your servers and privacy rules remain in OpenMaskit. Open its dashboard to manage them."
        )
        .foregroundStyle(CompanionTheme.secondary).fixedSize(horizontal: false, vertical: true)
      }
    } else {
      CompanionPanel("Local MCPs", detail: "\(model.profiles.count) approved") {
        HStack {
          Text(
            model.installation.paired
              ? "This Mac is paired." : "Configure the local MCP connection in Settings."
          )
          .foregroundStyle(CompanionTheme.secondary)
          Spacer()
          Button("Add Local MCP…") { model.approve() }
            .buttonStyle(CompanionButtonStyle(kind: .primary))
            .disabled(!model.installation.paired || !model.installation.ready)
        }
        if model.profiles.isEmpty {
          Text("No local MCP profiles added yet.")
            .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.muted)
        }
        ForEach(model.profiles) { profile in
          HStack(spacing: CompanionTokens.spaceSm) {
            Image(systemName: "checkmark.shield").foregroundStyle(CompanionTheme.teal)
            Text(profile.name).lineLimit(2)
            Spacer()
            Button("Add to OpenMaskit") {
              Task {
                await model.action(
                  ["register", profile.id, "--name", profile.name],
                  success: "MCP added. Configure its checks in OpenMaskit.")
              }
            }
            .disabled(!model.connectorRunning || !model.installation.canUseLocalConnector)
            .buttonStyle(CompanionButtonStyle())
          }
        }
        ForEach(model.installation.connectors ?? []) { connector in
          Label(
            connector.name + (connector.connected ? " · Connected" : " · Offline"),
            systemImage: connector.connected ? "link" : "link.badge.plus"
          )
          .font(CompanionTypography.caption)
          .foregroundStyle(connector.connected ? CompanionTheme.green : CompanionTheme.secondary)
        }
      }
      .disabled(model.busy)
    }
  }

  private var footer: some View {
    HStack(spacing: CompanionTokens.spaceSm) {
      if model.busy {
        ProgressView().controlSize(.mini)
        Text("Working…")
      } else {
        Image(systemName: "arrow.triangle.2.circlepath")
        Text("Manual updates")
      }
      Spacer()
      Button("Refresh") { Task { await model.refresh() } }
        .disabled(model.busy).buttonStyle(CompanionButtonStyle())
      SettingsLink { Label("Settings", systemImage: "gearshape") }
        .buttonStyle(CompanionButtonStyle())
    }
    .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
    .padding(.horizontal, CompanionTokens.spaceLg).padding(.vertical, 10)
    .background(CompanionTheme.surface)
  }

  private func notice(_ text: String, color: Color) -> some View {
    Text(text).font(CompanionTypography.caption).foregroundStyle(color)
      .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
  }
}
