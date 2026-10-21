# Update requirements

Automatic updates are not enabled. New managed installations use an immutable
connector relay image digest from
`ghcr.io/ricardomartins-gravitee/openmaskit-connector` together with the
currently pinned OpenMaskit image and Presidio version. A repository name or
tag alone is not a release verification.

The companion's local manager owns any future product-stack update process.
The connector repository owns connector package and relay image releases. Each
artifact must be verified for the intended protocol, platform and compatible
state before the manager applies an update.

Existing installations are preserved as they are. Moving relay-image
publication to the connector repository does not force a project, state,
container or volume migration. The manager must not automatically pull a new
image, recreate existing services or rewrite markers because the image prefix
changed. Any later manual update needs a verified compatible image, a complete
backup and a tested rollback plan.

Any future update mechanism must:

1. Authenticate release metadata using a pinned publisher identity or verified
   GitHub build provenance. HTTPS and a checksum downloaded beside an artifact
   are not sufficient on their own.
2. Check manifest schema, connector protocol, macOS architecture and supported
   state migrations. Reject incompatible artifacts and unrequested downgrades.
3. Stage verified executables and immutable image digests. Scope container
   changes to this app's own managed project. Never run installation commands
   received from the relay.
4. Wait for active calls, stop state writers and create a complete consistent
   backup before migration or recreation.
5. Verify service health and synthetic MCP privacy behavior after the change.
   Never use real mailbox tools for acceptance.
6. On failure, restore the prior compatible image and complete state snapshot.
   If recovery cannot be verified, stop and provide a clear recovery action.

Native app distribution also requires platform signing and notarization.
Development artifacts must not claim production signing. Any future automatic
update or login-start behavior requires a separate local user choice. No cron
job, scheduled task or unrelated container updater is installed.
