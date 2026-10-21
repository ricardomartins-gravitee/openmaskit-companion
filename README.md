# OpenMaskit Companion

An optional macOS desktop manager for a local OpenMaskit installation. Connect
to an existing installation, or manage a dedicated OpenMaskit and Presidio
Compose project with the separately maintained OpenMaskit Connector for locally
approved MCP servers.
This is a separate project, not a renamed OpenMaskit distribution, and is not
endorsed by upstream.

**Development alpha.** The macOS application is a development build until
signed and notarized. Automatic installation, login startup and automatic
updates are not enabled.

Companion is a **menu bar app**. Its menu bar icon is always available while
it runs; a configured launch opens no main window. Status, Open Dashboard,
Start All and Stop All are in the menu. Onboarding and Settings are its only
windows. Closing either hides the Dock icon and keeps the menu bar item and
services available. Reopen Settings or quit from the menu. Local MCP approval
and registration are under **Settings → Local MCPs**.
Only one Companion process runs per account, including copies opened from
different folders. Opening it again brings the existing Settings window forward;
each window belongs to the same app and Dock icon.
Quitting stops the local connector; managed containers keep their
normal state until explicitly stopped.

For a configured Companion installation, opening the app automatically starts
its installed services and previously approved connector. Docker Desktop is
opened if necessary, with a bounded wait for readiness. Disable this behavior
under **Settings → General → Start services and local MCPs when Companion opens**.
Manual stops are respected until the next app launch. Fresh onboarding and
externally managed installations never trigger automatic startup. No login item
or automatic installation/update is enabled; automatic startup never pulls images.
While its connector runs, Companion sends a protocol ping through OpenMaskit
once a minute to prevent the relay's idle timeout. It never calls MCP tools or
replays interrupted operations as part of these checks.

## Components

- **Native macOS app:** setup, status, start/stop, pairing and connector
  supervision.
- **Local manager:** retains product installation lifecycle, proxy setup and
  registration of approved MCPs as ordinary OpenMaskit HTTP targets.
- **OpenMaskit Connector dependency:** a separately versioned Python package
  that provides the host connector and relay protocol. The app bundles its
  executable and passes the companion's existing state directory explicitly.
- **Managed stack:** OpenMaskit, Presidio and the connector relay on ports
  9493/9494/9495, in the existing dedicated Compose project and data volume.

Raw MCP results enter the local OpenMaskit container before masking. AI clients
connect to OpenMaskit, never directly to the relay. No Docker socket is mounted.

Companion uses your standard Docker Desktop installation and its Docker Compose
tools. It manages one dedicated Compose project on this Mac. Installation and
connection choices are available in onboarding and Settings.

## Run from source

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and open
Docker Desktop. Clone this repository, then:

```sh
uv sync --frozen
uv run --frozen openmaskit-companion status
```

The local manager and macOS app use `~/.openmaskit-companion/` as their state
home. The connector dependency normally has a standalone default under
`~/.openmaskit-connector/`; the companion passes its existing companion home
explicitly so pairing credentials and approved profiles remain in place. Use
`--home /absolute/path` before the CLI command for isolated development state.
State directories are mode 0700 and credential files mode 0600 on POSIX. Protect
state with appropriate account permissions on other platforms.

## Choose an installation

On first launch, onboarding defaults to **Use existing**. Enter the dashboard
address (for example, `http://127.0.0.1:9473`) and choose **Connect to OpenMaskit**.
Companion verifies `/health` and saves only the address in its own private state.
It does not import, edit or replace your OpenMaskit database, rules, analyzers,
settings, encryption keys or service configuration. Keep using the existing
installation's service controls. Docker is not needed for this connection.

Only HTTP/HTTPS loopback origins on this Mac are supported; credentials, URL
paths, redirects and remote hosts are rejected. The existing service must expose
OpenMaskit's current health response with a connected database. Failed MCPs can
still be repaired through the dashboard. If OpenMaskit goes offline, the saved
connection remains selected and the dashboard button is disabled until it is
reachable again. Connecting or finishing setup never opens a browser automatically.

Use **Settings → Installation** to change the address or installation, manage
Companion-owned services, or configure pairing and the local connector.
The menu shows connection and service status; onboarding is shown only when no
installation has completed configuration. Changing installations stops
the app's local connector, keeps approved profiles and installation data, and
leaves existing services running. Companion's local connector controls are
currently available only for its managed installation.

### Managed installation

Choose **Companion installation** during onboarding or in Settings, then
**Set Up and Start OpenMaskit**. Docker Desktop must be available. This single
action prepares, starts and verifies all three services before completing setup.
If interrupted, retry **Start and Finish Setup**; existing Companion project
files, credentials, volumes and rules are reused. No other installation is adopted.

For the CLI, use a tested immutable connector relay image digest:


```sh
uv run openmaskit-companion prepare-managed --image ghcr.io/ricardomartins-gravitee/openmaskit-connector@sha256:RELEASE_DIGEST
uv run openmaskit-companion start
uv run openmaskit-companion pairing-code --name 'My computer'
uv run openmaskit-companion pair
```

The pairing code is single-use and expires after two minutes. Stop with
`openmaskit-companion stop`; data is retained. Existing managed installations
keep their current project, volume, state and containers. Changing the relay
image repository does not force a migration or recreate an existing stack.
The older `setup` CLI command remains preparation-only for compatibility.

To connect through the CLI instead:

```sh
uv run openmaskit-companion connect-existing --url http://127.0.0.1:9473
uv run openmaskit-companion status
```

## Approve a local MCP

Create a private JSON profile with an absolute `command`, an `args` array, and
optional `env` and `cwd`. Review it locally, then approve it and start the
connector:

```sh
uv run openmaskit-companion approve my-mcp --name 'My local MCP' --profile /absolute/path/profile.json
uv run openmaskit-companion connect
```

The connector runs the program with your user permissions; it does not sandbox
or install it or its dependencies. Keep the connector running. From another
terminal, register the approved profile in the companion-managed OpenMaskit:

```sh
uv run openmaskit-companion register my-mcp --name 'My local MCP'
```

Open **http://127.0.0.1:9493** to configure masking and privacy checks. Add
Presidio as `http://presidio-analyzer:3000`. Profile changes apply on the next
connector connection; stop the connector first for immediate local removal.
Revoking a paired computer immediately closes its channel.

## Distribution and verification

See [architecture and security](docs/architecture.md),
[development and acceptance](docs/development.md),
[security checks](docs/security-checks.md), and [update requirements](docs/updates.md).
The connector package and relay images are maintained in the
[OpenMaskit Connector repository](https://github.com/ricardomartins-gravitee/openmaskit-connector).
This repository pins its connector dependency through `uv.lock` and builds the
macOS app from locked dependencies. Development artifacts are not claimed to be
signed or notarized production releases.

The companion product targets macOS with Docker Desktop on the same computer.
The connector core is portable, but native Windows/Linux companion apps and
remote relay deployments require separate designs and acceptance. See
[SonarQube setup](docs/sonarqube.md) for the analysis configured for this
companion repository.

## Shared design system

The native app uses the same versioned design values as OpenMaskit's web UI,
through a revision-pinned native SwiftUI package. See
[design-system.md](docs/design-system.md) for integration and coordinated updates.
