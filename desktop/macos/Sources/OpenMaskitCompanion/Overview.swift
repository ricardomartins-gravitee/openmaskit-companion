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
          services
          localMCPs
          if let error = model.installation.error {
            notice(error, color: CompanionTheme.orange)
          }
          if !model.message.isEmpty {
            notice(model.message, color: CompanionTheme.secondary)
          }
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

  private var services: some View {
    CompanionPanel("Services", detail: model.installation.initialized ? nil : "Not set up") {
      if !model.installation.initialized {
        HStack(spacing: CompanionTokens.spaceLg) {
          VStack(alignment: .leading, spacing: CompanionTokens.spaceXs) {
            Text("Set up your local services").fontWeight(.medium)
            Text("A dedicated OpenMaskit, Presidio and relay installation.")
              .foregroundStyle(CompanionTheme.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          Spacer(minLength: 0)
          Button("Set Up OpenMaskit") {
            if let image = model.releaseImage {
              Task {
                await model.action(
                  ["setup", "--image", image],
                  success: "Installation prepared. Choose Start Services.")
              }
            } else {
              model.message =
                "This development build needs a published relay image. See the source setup instructions."
            }
          }
          .buttonStyle(CompanionButtonStyle(kind: .primary))
        }
      } else {
        if model.installation.services.isEmpty {
          Text("Services are stopped.").foregroundStyle(CompanionTheme.secondary)
        }
        ForEach(model.installation.services) { service in
          HStack(spacing: CompanionTokens.spaceSm) {
            Circle().fill(service.health == "healthy" ? CompanionTheme.green : CompanionTheme.muted)
              .frame(width: 6, height: 6)
            Text(service.title)
            Spacer()
            Text(service.health.isEmpty ? service.state : service.health)
              .font(.system(size: 11, design: .monospaced))
              .foregroundStyle(CompanionTheme.secondary)
          }
        }
        HStack(spacing: CompanionTokens.spaceSm) {
          Button("Start Services") {
            Task { await model.action(["start"], success: "Services are ready.") }
          }.buttonStyle(CompanionButtonStyle(kind: .primary))
          Button("Stop Services") {
            Task {
              await model.action(["stop"], success: "Services stopped. Your settings are saved.")
            }
          }.buttonStyle(CompanionButtonStyle(kind: .danger))
          Spacer()
          Button("Open OpenMaskit") {
            NSWorkspace.shared.open(URL(string: "http://127.0.0.1:9493")!)
          }.buttonStyle(CompanionButtonStyle())
        }
      }
    }
    .disabled(model.busy)
  }

  private var localMCPs: some View {
    CompanionPanel("Local MCPs", detail: "\(model.profiles.count) approved") {
      HStack(spacing: CompanionTokens.spaceSm) {
        Circle().fill(model.installation.paired ? CompanionTheme.teal : CompanionTheme.muted)
          .frame(width: 6, height: 6)
        Text(
          model.installation.paired
            ? "This Mac is paired."
            : "Pair this Mac to connect your approved local MCPs."
        )
        .foregroundStyle(CompanionTheme.secondary)
      }
      HStack(spacing: CompanionTokens.spaceSm) {
        Button(model.installation.paired ? "Pair Again" : "Pair This Mac") {
          Task { await model.pair() }
        }
        .disabled(!model.installation.initialized)
        .buttonStyle(CompanionButtonStyle())
        Button("Add Local MCP…") { model.approve() }
          .buttonStyle(CompanionButtonStyle(kind: .primary))
        Spacer()
        Button(model.connectorRunning ? "Stop Connector" : "Start Connector") {
          model.toggleConnector()
        }
        .disabled(!model.installation.paired)
        .buttonStyle(CompanionButtonStyle())
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
          .disabled(!model.connectorRunning)
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
