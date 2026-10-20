# Working on OpenMaskit Companion

This is a separate companion project. OpenMaskit remains the original application
and the existing fork must not be renamed. Read README.md and docs/architecture.md
before changing connection, installation, or update behavior.

- Keep commands, credentials, logs, runtime files and backups out of Git. Synthetic
  fixtures only in tests. Private development state belongs in ignored .runtime/.
- Host MCP commands are approved locally. Never accept executable commands, paths,
  environment overrides or working directories through a relay message.
- No shell execution. Invoke argument arrays, with bounded output and timeouts.
- Preserve complete MCP messages and bidirectional notifications. Never replay
  tool calls after disconnect. Do not log tool payloads or subprocess stderr.
- The native manager controls only its own dedicated Compose project. Do not
  mount the Docker socket into containers or modify other Docker projects.
- No automatic local installation, login item or updater is enabled by default.
  Updates require a verified compatible release, backup and rollback plan.
- An initial development build is not a signed/notarized production release.
- Keep connector and desktop UI independently runnable; the relay uses standard
  MCP HTTP to work with OpenMaskit without requiring a private fork transport.
- Use synthetic acceptance tests. Never invoke the user's real mailbox tools.
