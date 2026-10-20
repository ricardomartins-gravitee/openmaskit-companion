# Development and acceptance

```sh
uv sync --frozen --group dev
uv run pytest
uv run ruff check src scripts tests
uv run ruff format --check src scripts tests
uv run bandit --recursive src
uv run pytest --cov=openmaskit_companion --cov-branch --cov-report=xml
swift format lint --strict --recursive desktop/macos/Sources desktop/macos/Tests desktop/macos/Package.swift
swift build --package-path desktop/macos
swift test --package-path desktop/macos
uv run --group bundle python scripts/bundle.py
```

The test suite uses isolated temporary state, synthetic MCPs and ephemeral
loopback ports. It must cover pairing replay/expiry/revocation, browser-origin
rejection, credentials not appearing in state/status responses, strict local
launch approval, complete MCP round trips, notifications, disconnect cleanup,
message limits and project-scoped Docker operations.

The release gate additionally builds the actual relay image, runs it in a
disposable Compose project with real OpenMaskit and Presidio, verifies masking and
alias reversal, and removes only the disposable project and synthetic data.
Source tests alone are not approval to deploy to a user's real mail installation.

The first native app targets macOS 14+, using SwiftUI and a bundled standalone
Python backend. It has no shell command interpolation, no local control HTTP
server and no automatic login/startup behavior. The backend can run independently
through its CLI. Linux/Windows CLI builds use the same Python implementation.
Apple Silicon and Intel macOS have separate native test and packaging jobs.
Intel reuses our [verified cryptography wheel](intel-wheel.md) from the same
workflow run; packaged downloads do not compile dependencies on a user's Mac.

Full Xcode supplies XCTest for the hosted macOS policy tests. If a local Mac has
only Command Line Tools, run `python scripts/test_macos_policy.py` to check all
eight menu visibility combinations without XCTest. Also verify native behavior:
Settings preferences persist, each menu option works independently, closing to
the menu bar removes the Dock icon, Show restores the window and Dock icon,
Settings remains reachable while hidden, and Quit terminates the connector.

`python scripts/test_macos_desktop.py` additionally checks the actual AppKit
activation policy, preference persistence, adapter effects and absence of redundant
state publications. Hosted XCTest runs both the reducer and desktop-adapter suites.
Closing must not trigger a reopen through SwiftUI's `onAppear`; only explicit
menu/Dock/settings intent can request the main window.

`scripts/manager_acceptance.py --image <published-immutable-image>` runs actual
CLI setup, container start, pairing, local approval, connector launch, idempotent
registration, status redaction, a synthetic MCP call and stop. It requires the
product ports to be free, creates its own random project and deletes only that
disposable installation. The Linux distribution job runs it before publishing
download artifacts. It must never adopt the user's existing installation.
