# OpenMaskit Companion

An optional macOS desktop manager for a local OpenMaskit installation. It
manages a dedicated OpenMaskit and Presidio Compose project and integrates the
separately maintained OpenMaskit Connector for locally approved MCP servers.
This is a separate project, not a renamed OpenMaskit distribution, and is not
endorsed by upstream.

**Development alpha.** The macOS application is a development build until
signed and notarized. Automatic installation, login startup and automatic
updates are not enabled.

The app's **Settings** screen has independent options for showing a menu bar
icon and keeping the app running in the menu bar when its main window closes.
These options are off initially. Monitoring continues while the window is
hidden. Quitting stops the local connector; managed containers keep their
normal state until explicitly stopped.

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

## Managed installation

Use a tested immutable connector relay image digest:

```sh
uv run openmaskit-companion setup --image ghcr.io/ricardomartins-gravitee/openmaskit-connector@sha256:RELEASE_DIGEST
uv run openmaskit-companion start
uv run openmaskit-companion pairing-code --name 'My computer'
uv run openmaskit-companion pair
```

The pairing code is single-use and expires after two minutes. Stop with
`openmaskit-companion stop`; data is retained. Existing managed installations
keep their current project, volume, state and containers. Changing the relay
image repository does not force a migration or recreate an existing stack.

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
