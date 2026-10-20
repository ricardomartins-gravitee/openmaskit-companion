# Development and acceptance

```sh
uv sync --frozen --group dev
uv run pytest
swift build --package-path desktop/macos
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
