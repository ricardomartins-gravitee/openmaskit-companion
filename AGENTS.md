# Working on OpenMaskit Companion

This repository contains the macOS desktop manager for OpenMaskit. OpenMaskit
remains the original application and the existing fork must not be renamed. Read
README.md and docs/architecture.md before changing installation, connector
integration, or update behavior.

- Keep commands, credentials, logs, runtime files and backups out of Git. Use
  synthetic fixtures only. Private development state belongs in ignored
  `.runtime/`.
- Preserve the existing `~/.openmaskit-companion/` state layout, managed Compose
  project markers, volumes, ports and service behavior. Do not force a state,
  project or container migration.
- The local manager controls only its dedicated Compose project. Never mount the
  Docker socket into containers or modify other Docker projects.
- The separately maintained `openmaskit-connector` dependency owns connector
  launch and relay protocol implementation. Keep the macOS app and its thin CLI
  integration independently testable; pass the existing companion home
  explicitly to connector commands.
- Never accept executable commands, paths, environment overrides or working
  directories through a relay message. Do not log MCP payloads or subprocess
  stderr. Preserve complete MCP messages and bidirectional notifications; never
  replay calls after disconnect.
- Use argument arrays, not shell command interpolation. Bound subprocess output
  and timeouts.
- No automatic local installation, login item or updater is enabled by default.
  Updates require a verified compatible release, backup and rollback plan.
- An initial development build is not a signed/notarized production release.
- Use synthetic acceptance tests. Never invoke the user's real mailbox tools.
