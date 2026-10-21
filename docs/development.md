# Development and acceptance

Install the locked dependencies and run the companion checks:

```sh
uv sync --frozen --group dev
uv run --frozen --no-sync --no-build pytest
uv run --frozen --no-sync --no-build ruff check src scripts tests
uv run --frozen --no-sync --no-build ruff format --check src scripts tests
uv run --frozen --no-sync --no-build bandit --recursive src
uv run --frozen --no-sync --no-build pytest --cov=openmaskit_companion --cov-branch --cov-report=xml
swift format lint --strict --recursive desktop/macos/Sources desktop/macos/Tests desktop/macos/Package.swift
swift build --package-path desktop/macos
swift test --package-path desktop/macos
uv run --frozen --no-sync --no-build python scripts/bundle.py
```

The macOS product is SwiftUI/AppKit with a local Python manager. The
`openmaskit-connector` package is a separately versioned dependency pinned to a
full immutable Git source revision in `uv.lock`. The app bundles its executable
and passes the existing companion state directory to connector commands. Keep
the CLI delegation and app bundle launch behavior covered by synthetic tests.

## CI and acceptance

Companion product builds and tests run on Apple Silicon and Intel macOS. There
are no Windows or Linux companion product jobs. Linux CI may still run Python
quality checks and manager integration tests where containers are required.
The connector's own cross-platform tests, container image builds, relay
acceptance and native-wheel build/release workflow are maintained in the
[connector repository](https://github.com/ricardomartins-gravitee/openmaskit-connector).
This repository uses the connector revision pinned in `uv.lock`; do not assume
that a connector image or native dependency release has been published unless
the corresponding immutable artifact is verified.

Tests use isolated temporary state, synthetic MCP servers and loopback ports.
They cover state compatibility, manager operations scoped to its dedicated
project, relay pairing and registration integration, status redaction, and
native UI behavior. The container acceptance stack is disposable and must not
adopt or modify an existing user project or mailbox data.

The macOS tests cover preference persistence and menu-bar behavior: independent
settings, closing the window while preserving intended background operation,
showing the window from the menu or Dock, and connector termination on Quit.
Hosted XCTest runs both policy and desktop adapter suites. On local machines
without XCTest, `scripts/test_macos_policy.py` and
`scripts/test_macos_desktop.py` provide Command Line Tools acceptance checks.

The connector owns its relay and container acceptance gate. This repository's
manager integration must continue to preserve existing installation state and
containers when the connector dependency or image reference changes. No test
may invoke real mailbox tools.

## Intel macOS dependency

The connector repository owns the Intel cryptography/OpenSSL build helper and
durable dependency release workflow. Companion CI consumes the corresponding
connector-owned reusable build/verification path and same-run wheel artifact;
it does not own or publish duplicate native dependency releases. See the
[connector's Intel dependency build](https://github.com/ricardomartins-gravitee/openmaskit-connector/blob/main/docs/intel-wheel.md).

CI installs registry dependencies with `--no-build` and skips the Git-sourced
connector during that step. It then verifies the separately checked-out connector
commit against `dependencies/connector.json`, packages only that reviewed
pure-Python source with the locked Hatchling backend, and installs its wheel with
required SHA-256 hashes and no dependency resolution. No registry dependency
falls back to compiling.
