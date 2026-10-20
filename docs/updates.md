# Update requirements

Automatic updates are not yet enabled. This is an explicit release gate, not an
unverified download-and-execute placeholder. Initial setup accepts an immutable
companion image digest in the expected repository; it uses the bundled, tested
OpenMaskit digest and Presidio version.

## Next implementation

The companion app will own an updater shared with the headless manager:

1. Fetch a signed release manifest, verified against a pinned publisher key or
   a pinned GitHub Actions artifact identity. HTTPS or a checksum beside the
   download alone is not sufficient to authenticate a software publisher.
2. Check manifest schema, bridge protocol, OS/architecture and supported data
   migrations. Select an explicitly tested combination of components. Reject
   downgrades unless the operator requests a recovery operation.
3. Stage verified native artifacts and images pinned by digest. Container updates
   apply only to this app's managed project. Keep local MCP dependency upgrades
   separately approved; installation scripts must not come from relay messages.
4. Wait for active calls, enter maintenance mode, stop state writers, and create
   a complete consistent backup including encryption key, aliases and settings.
5. Apply compatible migrations and recreate only changed managed containers.
6. Check expected versions, databases, saved rule counts, analyzer connectivity
   and synthetic MCP protection. Do not call real mailbox tools for acceptance.
7. On failure, restore the retained image and complete compatible data snapshot.
   If recovery cannot be verified, stop and give a clear recovery action.

Native executable updates must also use the platform's signing/notarization
mechanism. macOS distribution needs Developer ID signing credentials. CI cannot
invent an Apple developer identity. Development artifacts must never claim to
be signed/notarized production releases.

The app will offer manual, notify-only and automatic modes. Changing to automatic
mode and enabling a login item will require a local user choice. Check on launch
and wake; background checks require the app to run. No cron job, Codex scheduled
task or unrelated container auto-updater is installed.
