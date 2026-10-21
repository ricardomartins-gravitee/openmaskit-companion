# Security checks

This repository's validation workflow checks the companion manager and macOS
app. It runs repository secret and vulnerability scans, Python quality and
dependency checks, manager integration acceptance, and native Swift lint and
tests. Pull request jobs do not publish releases. Scanner failures and malformed
reports fail closed; reports that might contain source excerpts stay in
ephemeral runner storage.

## Companion checks

The quality workflow runs Ruff linting and formatting across Python source,
scripts and tests; Bandit against production Python; pytest branch coverage
with an enforced 80% overall floor; and `pip-audit` against locked dependencies.
The macOS jobs lint Swift using Apple's formatter and run XCTest. The manager
integration tests use synthetic state and must act only on their disposable,
dedicated Compose project. They must preserve existing managed installations
and never access real mailbox tools.

Gitleaks scans full repository history with upstream default rules and full
redaction. Trivy scans tracked repository content for vulnerabilities,
misconfigurations and secrets. HIGH and CRITICAL findings block checks,
including unfixed findings. Generated private runtime directories are
excluded. Workflow configuration is linted, and Actions are pinned to reviewed
immutable revisions.

The OpenMaskit Connector repository owns cross-platform connector checks, relay
image scans and publication, synthetic end-to-end container acceptance, and the
Intel cryptography/OpenSSL native dependency build and release. The companion
pins a connector source revision in `uv.lock` and consumes the connector-owned
verification/build artifact path. These artifacts must be verified before use;
their publication is not implied by a source pin.

## SonarQube Cloud

The companion repository is connected to the configured SonarQube Cloud
project. Its automatic analysis is separate from the blocking GitHub checks and
does not import coverage reports. See [SonarQube setup](sonarqube.md) for the
current account and project configuration.

## Local checks

Run Trivy against a clean checkout and keep its potentially sensitive report
private:

```sh
trivy repo --scanners vuln,misconfig,secret \
  --severity HIGH,CRITICAL --exit-code 1 \
  --format json --output /tmp/trivy-report.json .
```

Run Gitleaks across all available history; shallow clones cannot provide the
same history coverage:

```sh
gitleaks git --redact=100 --report-format=json \
  --report-path /tmp/gitleaks-report.json --no-banner .
```

Rotate and remove any confirmed credential. Do not use an ignore entry as
remediation. Scanners do not replace local credential generation or access
controls.
