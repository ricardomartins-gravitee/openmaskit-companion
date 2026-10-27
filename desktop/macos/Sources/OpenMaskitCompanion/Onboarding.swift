import SwiftUI

struct InstallationSetup: View {
  @ObservedObject var model: CompanionModel
  @State private var choice = "existing"
  @State private var address = "http://127.0.0.1:9473"

  var body: some View {
    CompanionPanel(
      model.installation.configured ? "Choose installation" : "Welcome to OpenMaskit Companion"
    ) {
      Text("Connect to OpenMaskit on this Mac, or let Companion create and manage an installation.")
        .foregroundStyle(CompanionTheme.secondary).fixedSize(horizontal: false, vertical: true)
      Picker("Installation", selection: $choice) {
        Text("Use existing").tag("existing")
        Text("Companion installation").tag("managed")
      }
      .pickerStyle(.segmented)
      if choice == "existing" {
        Text("Keep your existing OpenMaskit").fontWeight(.medium)
        Text(
          "Your servers, rules, analyzers and settings stay in their current installation. Companion saves its address and checks its status."
        )
        .foregroundStyle(CompanionTheme.secondary).fixedSize(horizontal: false, vertical: true)
        LabeledContent("Dashboard address") {
          TextField("http://127.0.0.1:9473", text: $address)
            .textFieldStyle(.roundedBorder)
            .accessibilityLabel("Existing OpenMaskit dashboard address")
            .accessibilityIdentifier("setup.address")
            .onSubmit { Task { await model.connectExisting(address) } }
        }
        Button("Connect to OpenMaskit") { Task { await model.connectExisting(address) } }
          .accessibilityIdentifier("setup.connect")
          .buttonStyle(CompanionButtonStyle(kind: .primary))
      } else {
        Text(
          model.installation.initialized
            ? "Use your prepared Companion installation" : "Create an installation"
        )
        .fontWeight(.medium)
        Text(
          "Requires Docker Desktop. Companion prepares OpenMaskit, Presidio and the local MCP relay, starts them, and checks that OpenMaskit is ready."
        )
        .foregroundStyle(CompanionTheme.secondary).fixedSize(horizontal: false, vertical: true)
        Text(
          "Existing Companion data is reused. Other installations and their settings are kept in place."
        )
        .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
        RuntimeRequirementsView(model: model)
        Button(
          model.installation.initialized ? "Start and Finish Setup" : "Set Up and Start OpenMaskit"
        ) {
          Task { await model.configureManaged() }
        }
        .buttonStyle(CompanionButtonStyle(kind: .primary))
        .accessibilityIdentifier("setup.managed")
        .disabled(
          model.requirements?.ready != true || model.checkingRequirements
            || (model.installation.mode == .managed && model.installation.configured
              && model.installation.ready)
        )
      }
      if model.installation.configured {
        Text(
          "Changing installations stops the local MCP connection. Approved profiles and installation data are kept, and existing services keep running."
        )
        .font(CompanionTypography.caption).foregroundStyle(CompanionTheme.secondary)
      }
    }
    .disabled(model.busy)
    .task(id: choice) {
      if choice == "managed" { await model.checkRequirements() }
    }
    .onAppear {
      choice =
        model.installation.mode == .managed && model.installation.configured
        ? "managed" : "existing"
      if model.installation.mode == .existing, let saved = model.installation.dashboard {
        address = saved
      }
    }
  }
}

struct RuntimeRequirementsView: View {
  @ObservedObject var model: CompanionModel

  var body: some View {
    VStack(alignment: .leading, spacing: CompanionTokens.spaceSm) {
      Text("Requirements").fontWeight(.medium)
      if let report = model.requirements {
        ForEach(report.checks) { check in
          HStack(alignment: .top) {
            Image(
              systemName: check.state == "ready" ? "checkmark.circle" : "exclamationmark.circle"
            )
            .foregroundStyle(check.state == "ready" ? CompanionTheme.accent : CompanionTheme.orange)
            .accessibilityHidden(true)
            VStack(alignment: .leading) {
              Text(
                check.title
                  + (check.state == "ready"
                    ? " · Ready" : (check.state == "blocked" ? " · Waiting" : " · Needs attention"))
              )
              if check.state == "needs_attention" {
                Text(check.detail).font(CompanionTypography.caption)
                  .foregroundStyle(CompanionTheme.secondary)
              }
            }
          }
          .accessibilityElement(children: .combine)
        }
      } else {
        Text(model.requirementsError.isEmpty ? "Checking requirements…" : model.requirementsError)
          .foregroundStyle(CompanionTheme.secondary)
      }
      if !model.requirementsError.isEmpty && model.requirements != nil {
        Text(model.requirementsError).foregroundStyle(CompanionTheme.orange)
      }
      if let report = model.requirements, !report.ready && report.canStartDocker {
        Button("Open Docker Desktop") { Task { await model.openDockerDesktop() } }
          .buttonStyle(CompanionButtonStyle())
      }
      Button(model.checkingRequirements ? "Checking…" : "Check Again") {
        Task { await model.checkRequirements() }
      }
      .buttonStyle(CompanionButtonStyle()).disabled(model.checkingRequirements)
    }
  }
}

struct InstallationFeedback: View {
  @ObservedObject var model: CompanionModel
  var body: some View {
    if model.busy {
      HStack(alignment: .top, spacing: CompanionTokens.spaceSm) {
        ProgressView().controlSize(.small)
        Text(model.progress.isEmpty ? "Working…" : model.progress)
          .fixedSize(horizontal: false, vertical: true)
      }
      .foregroundStyle(CompanionTheme.secondary)
      .accessibilityElement(children: .combine)
    }
    if !model.message.isEmpty {
      Text(model.message).foregroundStyle(CompanionTheme.secondary)
        .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
    }
  }
}
