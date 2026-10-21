# Architecture and trust boundaries

Status: development implementation, connector protocol version 1.

## Repository boundary

This repository owns the SwiftUI/AppKit macOS app, local product manager, and
managed OpenMaskit/Presidio lifecycle. The
[OpenMaskit Connector repository](https://github.com/ricardomartins-gravitee/openmaskit-connector)
owns the versioned Python connector package, relay protocol and relay images.
The companion consumes the connector as a locked dependency and bundles it in the app's backend executable. Its thin CLI integration delegates connector operations and passes
the existing `~/.openmaskit-companion/` state home explicitly.

The connector's standalone default remains `~/.openmaskit-connector/`. The
companion's explicit home preserves existing pairing credentials, profiles and
state layout. This integration does not silently copy, rename or migrate user
state.

The relay exposes standard MCP Streamable HTTP, so OpenMaskit's existing HTTP
target support is sufficient. No private OpenMaskit transport is required.

```text
AI client <-> OpenMaskit:9494 <-> connector relay MCP endpoint
                    |                         ^
                 Presidio                     | authenticated outbound WebSocket
                                              |
                         macOS app -> local connector -> approved stdio MCP
```

## Permissions and credentials

Pairing requires the local manager's relay-admin credential. Pairing codes have
144 bits of entropy, expire in 120 seconds, are stored hashed in memory and are
consumed once. The public pairing endpoint is rate limited globally. Each
paired connector receives a separate 256-bit token; only its hash is retained
by the relay. Revoking it closes the live channel and every session. Relay
restarts invalidate pending pairing codes but preserve paired identities.

The proxy credential is distinct from admin and connector credentials.
OpenMaskit stores its proxy header through its normal encrypted HTTP
configuration path. The connector relay rejects requests with a browser Origin.
MCP Host validation uses the SDK's DNS-rebinding protection. Host-facing ports
are bound to loopback. Remote TLS deployments require a separate design and
acceptance.

The host stores exact absolute executable paths, argument arrays, environment
and working directories in a private file. The relay can select only locally
approved profiles; it never supplies commands, paths, environment overrides or
working directories. Profiles are loaded once per connection. Child stderr is
discarded and MCP payloads are never logged. State is permission-protected, not
independently encrypted; OS keychain storage is planned. The connector is not a
sandbox for the MCP.

## Messages and lifecycle

The connector hello frame contains protocol version and approved profile IDs
and display names only. Relay open frames name a profile and fresh random
session ID. Message frames carry validated complete MCP JSON-RPC objects;
close/closed terminate a session. The SDK handles public Streamable HTTP
session semantics. Bidirectional requests, responses, notifications and
cancellation cross the bridge. Neither side fabricates MCP initialization
capabilities.

Limits: 1 MiB messages, 32 queued messages per session, four sessions per
computer, 32 profiles per connector, 16 paired computers, 64 active profile
managers per relay process, and 300-second idle HTTP sessions. No persisted
payload queue or replay on reconnection. Interrupted calls have uncertain
outcomes; callers must not automatically retry side-effecting tools. Disconnect
terminates child processes and wakes outstanding HTTP sessions. Failures never
bypass OpenMaskit's privacy checks or connect AI clients directly to raw MCPs.

## Managed local installation

### Installation selection and existing services

`installation.json` under the private Companion state directory records the
selected local origin, mode and completion state. It is an atomic, mode-0600
pointer, not a copied OpenMaskit configuration. Existing managed state without
this file is recognized in place. A legacy project that was only prepared and
has no containers returns to onboarding; stopped or temporarily unavailable
configured installations keep their selection.

Existing mode performs read-only `GET /health` requests without proxy environment
variables, redirects or credentials. Only HTTP/HTTPS loopback IPs or `localhost`
are accepted. Responses have a size limit, timeouts and a schema check. A
connected database is required; degraded MCPs do not prevent access to the
dashboard for repair. Only readiness, aggregate health and a server count are
returned to the UI. Target names and health error bodies are not exposed.

Existing mode rejects managed service, relay administration, pairing and
registration operations before Docker or credential access. It never opens the
existing installation's files or writes its APIs. The dashboard opens only after
a fresh successful health check; setup and attachment do not open it. Onboarding
is for an unconfigured installation; service lifecycle and connection choices
remain in Settings after setup. Switching stops only the app-owned host connector
and preserves profiles, credentials and running services.

### Dedicated project

The manager controls only its dedicated
`openmaskit-companion-<installation-id>` Compose project in the private
companion state directory. It validates project names and never adopts, stops
or removes other Docker projects. OpenMaskit keeps its separate persistent
volume and key. Presidio and relay share the internal network with OpenMaskit;
the relay also joins the dedicated host-facing network required for loopback
port publishing. OpenMaskit retains outbound access for its HTTP MCP targets.
Only the host manager invokes Docker, using argument arrays and fixed project
files. No container gets the Docker socket.

Existing installations keep their state, project marker, volume, service names
and running containers. Moving relay-image ownership to the connector repository
does not automatically pull a new image, recreate containers or migrate state.
Any later manual update must use a verified compatible image, a complete backup
and a rollback plan. No automatic update or login item is enabled. Quitting the
app stops the local host connector; it does not stop managed containers.

## App launch and menu bar operation

The native app starts as an accessory application. It has no configured main
dashboard window; native AppKit window controllers host SwiftUI onboarding and
Settings only. Dock reopening opens Settings (or unfinished onboarding). If both
menu visibility options are disabled, Settings and Dock presence remain reachable.
The two existing menu visibility preferences are retained independently.

Before creating scenes or starting services, Companion acquires a private,
per-account kernel file lock in its Application Support directory. Duplicate
launches notify the running app to reveal Settings and exit without starting
another connector. The lock is released automatically on normal exit or a crash;
its file is retained to prevent inode replacement races. A running-app check also
hands off to an older installed build during an upgrade. Onboarding and Settings
reuse one controller each and share a single app process and Dock identity.

Automatic runtime startup defaults on and is separately configurable. A loaded,
configured managed selection is required. A once-per-process gate prevents
monitoring, opening menus or reopening Settings from reversing a manual stop.
The native coordinator probes only a validated local Docker context, opens the
installed Docker Desktop app if necessary, and uses a two-minute readiness
deadline with individually bounded probes. It
starts Presidio and the relay before launching a previously paired/approved host
connector. OpenMaskit is then started, saved active local connections are restored,
and the full project is checked for health. Existing images are reused with
`--pull never`; no setup, image update, new pairing or profile approval is automatic.

Connector reconnection reinitializes only custom HTTP targets whose exact relay
URL belongs to this paired computer and an approved/advertised profile. Inactive,
unrelated and marketplace targets are excluded. The ordinary deactivate/activate
API restores sessions without replacing configuration, rules, aliases or secrets.
Failed reconnection is reported and leaves the target disconnected for repair.
No interrupted MCP call is replayed. App monitoring detects a running connector's
offline-to-online transition; an explicitly stopped connector stays stopped.
While the app-owned connector is online, monitoring sends at most one keepalive
batch per minute to those same active, approved targets through OpenMaskit's MCP
endpoint. These are bounded protocol `ping` requests, retaining the relay's
five-minute idle-session limit. They never invoke tools, bypass masking, reset
sessions or retry interrupted calls. Failed checks are reported for repair.
