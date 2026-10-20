# OpenMaskit Companion

An optional desktop manager and outbound connector for local MCP servers.
Works with OpenMaskit through its existing HTTP MCP support. This is a separate
project, not a renamed OpenMaskit distribution, and is not endorsed by upstream.

**Development alpha.** The relay and connector are under active validation.
The macOS application is a development build until signed and notarized.
Automatic installation, login startup and automatic updates are not enabled.

The macOS app's **Settings** screen includes independent options to show a menu
bar icon and to keep running in the menu bar when the main window closes. Closing
to the menu bar hides the Dock icon; the menu can reopen the window or quit. Both
options are off initially and saved when changed. Monitoring continues while the
window is hidden. Quitting stops the local connector; managed containers retain
their normal running state until explicitly stopped.

## Components

- **Native macOS app:** setup, status, start/stop, pairing and connector supervision.
- **Standalone connector:** launches only MCP profiles approved locally; opens an
  authenticated outbound WebSocket to the local relay. No inbound host service.
- **Private relay container:** forwards complete MCP sessions and exposes standard
  Streamable HTTP to OpenMaskit. No changes to the OpenMaskit fork are required.
- **Managed stack:** OpenMaskit, Presidio and relay, on ports 9493/9494/9495. Separate
  project and persistent storage; no adoption of existing services or mail data.

Raw results enter your local OpenMaskit container before masking. AI clients
connect to OpenMaskit, never directly to the relay. No Docker socket is mounted.

## Run from source

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and open
Docker Desktop. Clone this repository, then:

```sh
uv sync --frozen
uv run --frozen openmaskit-companion status
```

State defaults to `~/.openmaskit-companion/`; use `--home /absolute/path` before
the command for an isolated installation. Each new installation gets its own
Docker project and data volume; the fixed service ports must still be available.
State directories are mode 0700 and
files containing credentials are mode 0600 on POSIX. Do not publish this directory.
Windows requires a private user-profile directory and appropriate account ACLs.

### Managed installation

Use the immutable companion image digest published by a tested release:

```sh
uv run openmaskit-companion setup --image ghcr.io/ricardomartins-gravitee/openmaskit-companion@sha256:RELEASE_DIGEST
uv run openmaskit-companion start
uv run openmaskit-companion pairing-code --name 'My computer'
uv run openmaskit-companion pair
```

The pairing command prompts for the short-lived code. It is single-use and
expires after two minutes. Start a new pairing if it expires. Existing private
settings are not imported. Stop with `openmaskit-companion stop`; data is retained.

### Approve a local MCP

Create a private JSON file with `command` (an absolute path), `args`, optional
`env` and `cwd`. Review it locally, then approve it:

```sh
uv run openmaskit-companion approve my-mcp --name 'My local MCP' --profile /absolute/path/profile.json
uv run openmaskit-companion connect
```

Keep the connector running. From another terminal, register the approved profile
in the companion-managed OpenMaskit:

```sh
uv run openmaskit-companion register my-mcp --name 'My local MCP'
```

Open **http://127.0.0.1:9493** to configure masking and privacy checks. Add Presidio
as `http://presidio-analyzer:3000`. The connector does not install Thunderbird,
its extension, Node, Python or any other MCP's dependencies. Programs run with
your user permissions, not in a sandbox. Reconnect after changing approved
profiles. `forget` affects the next connector connection; stop the connector
first for immediate local removal. `revoke` immediately closes a paired computer.

## Distribution and verification

See [architecture and security](docs/architecture.md),
[development and acceptance](docs/development.md), and
[update design](docs/updates.md). GitHub builds the headless tool and macOS app
from locked dependencies. Releases retain checksums and source provenance.
No claim of Apple signing/notarization is made for development artifacts.

This project's initial scope is macOS with Docker Desktop on the same computer.
The connector core is portable; remote deployments, native Windows/Linux apps,
OS keychain integration and automatic updates need separate acceptance.
