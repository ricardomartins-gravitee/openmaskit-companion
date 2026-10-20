# Architecture and trust boundaries

Status: initial development implementation, protocol version 1.

## Repository boundary

OpenMaskit remains a maintained native GitHub fork with its existing name. This
repository owns desktop packaging, host supervision, approved local launchers,
the outbound bridge and relay. The relay presents ordinary MCP Streamable HTTP,
so OpenMaskit's existing HTTP target support is sufficient. No companion-specific
transport or desktop packaging code needs to be added to the fork.

```text
AI client <-> OpenMaskit:9494 <-> private relay MCP endpoint
                    |                   ^
                 Presidio               | authenticated outbound WebSocket
                                        |
                                  host connector <-> approved stdio MCP
```

## Permissions

Pairing requires the local manager's relay admin credential. Pairing codes have
144 bits of entropy, expire in 120 seconds, are stored hashed in memory and are
consumed once. The public pairing endpoint is rate limited globally. Each paired
connector receives a separate 256-bit token; only its hash is retained by the
relay. Revoking it closes the live channel and every session. Relay restarts
invalidate pending pairing codes but preserve paired identities.

The proxy credential is distinct from admin and connector credentials. OpenMaskit
stores its proxy header through its encrypted normal HTTP configuration path.
Relay requests with a browser Origin are rejected. MCP Host validation uses the
SDK's DNS-rebinding protection. Only loopback host ports are published. Native
connector endpoints are loopback-only in this release; remote TLS deployments
require a separate design and acceptance.

The host stores exact absolute executable paths, argument arrays, environment and
working directories in a private file. It never accepts them from the relay.
Profiles are loaded once per connection. Child stderr is discarded; MCP payloads
are never logged. State is permission-protected, not independently encrypted;
OS keychain storage is planned. The connector is not a sandbox for the MCP.

## Messages and lifecycle

The hello frame contains protocol version and approved profile IDs/display names
only. Relay open frames name a profile and fresh random session ID. Message frames
carry validated complete MCP JSON-RPC objects; close/closed terminate a session.
The SDK handles the public Streamable HTTP session semantics. Bidirectional
requests, responses, notifications and cancellation cross the bridge. Neither
side fabricates MCP initialization capabilities.

Limits: 1 MiB messages, 32 queued messages per session, four sessions per computer,
32 profiles per connector, 16 paired computers, 64 active profile managers per
relay process, 300-second idle HTTP sessions. No persisted payload queue or replay
on reconnection. Interrupted calls have uncertain outcomes; callers must not
automatically retry side-effecting tools. Disconnect terminates child processes
and wakes outstanding HTTP sessions. Failures never bypass OpenMaskit privacy
checks or connect AI clients directly to the raw MCP.

## Local manager

The manager controls a dedicated `openmaskit-companion-<installation-id>` Compose
project in its own private state directory. Each new installation gets an
independent project/volume. The exact legacy early-alpha project name remains
supported for existing markers. Project names are validated before Docker runs.
The manager never adopts, stops or removes other Docker projects.
OpenMaskit has a separate persistent volume and key; Presidio and relay share an
internal network with OpenMaskit. Presidio joins only that network. The relay also
joins a dedicated host-facing network for the published loopback connection;
Docker Desktop cannot reliably publish a service connected only to an internal
network. OpenMaskit separately has outbound network access for HTTP MCPs.
Only the native manager invokes the host's Docker executable; no container gets
the Docker socket. Docker access is powerful and is not delegated to MCP tools.

Automatic updates and login items are off. A foreground connector retries an
empty connection with bounded backoff while the app runs; this is not a scheduled
installer. Laptop sleep disconnects local MCPs. Nothing makes them available
while the host is asleep.
