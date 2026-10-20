# Security checks

The validation workflow calls the reusable security workflow independently of
the test matrix. It runs on pull requests and pushes through that call, and can
also be started manually with `workflow_dispatch`. It has no schedule, requires
no repository secrets, and receives read-only repository access.

The workflow runs two blocking checks:

- **Gitleaks 8.30.1** scans the full Git history (`fetch-depth: 0`) using the
  upstream default rules. The release archive is checked against its published
  SHA-256 before execution. Redaction is set to 100%, and the scanner's JSON
  report is written to the runner's temporary directory only. There is no
  baseline or ignore list, and inline `gitleaks:allow` comments are ignored.
- **Trivy 0.70.0** scans the repository for vulnerabilities, IaC
  misconfigurations, and secrets. The `aquasecurity/trivy-action` is pinned to
  immutable commit `a9c7b0f06e461e9d4b4d1711f154ee024b8d7ab8` (release v0.36.0);
  the scanner version is explicitly pinned. HIGH and CRITICAL findings fail
  the check, including unfixed vulnerabilities. JSON output stays in the
  ephemeral runner temp directory and is neither logged nor uploaded. Only
  finding counts and vulnerability or misconfiguration IDs are printed; secret
  finding details are withheld. Generated/runtime directories are excluded.

The workflow also pins `actions/checkout` v7.0.1 to commit
`3d3c42e5aac5ba805825da76410c181273ba90b1`. It does not use
`pull_request_target`, write permissions, third-party report upload, or scanner
output that could reveal secret material in logs.

Each built companion image is also scanned by Trivy before real-container
acceptance or publication. HIGH/CRITICAL vulnerabilities and secrets block the
image; unfixed findings are included. Scan reports stay private to the ephemeral
runner. A tested report helper prints only counts and validated advisory IDs.
Missing or malformed reports fail rather than appearing clean.
The report reader accepts only the fixed Trivy and Grype JSON filenames inside
`RUNNER_TEMP`, rejects symlinks and other locations, and limits input to 16 MiB.
Release downloads require HTTPS for the initial request and every redirect,
as well as verifying the archive checksum.

## Code quality and test coverage

The independent reusable quality workflow locks its tools in `uv.lock` and runs:

- **Ruff** linting and formatting across production Python, tests and scripts.
- **Bandit** security analysis of all production Python. Required fixed-argument
  Docker process calls and best-effort private-error cleanup have narrow inline
  exceptions with rationale; there are no global rule exclusions. Its raw report
  stays on the ephemeral runner because it can contain source excerpts.
- **pytest-cov / coverage.py**, including branches, with an enforced 80% overall
  coverage floor and downloadable HTML/XML reports. Production modules are not
  omitted to reach the threshold. The current baseline is approximately 85%.
- **pip-audit** against the exact runtime, test and build dependencies exported
  from `uv.lock`, retaining their hashes. Any known vulnerability fails this
  check, including severities below Trivy's HIGH/CRITICAL threshold.

All CI dependency installation disallows source builds. Intel macOS uses a
dedicated [cryptography wheel build](intel-wheel.md): an explicit compilation of
the hash-verified upstream source, using locked binary Python build tools and
the upstream Cargo lockfile. Trivy scans its Rust inputs and Python component;
Grype 0.121.0 additionally checks the embedded OpenSSL version using its CPE.
Native cryptographic vectors, tamper rejection and static linkage must pass
before the wheel is shared with tests and packaging in the same workflow run.
Consumers verify the commit, source checksum, wheel metadata and wheel checksum,
then install that wheel with `--no-build --no-deps --require-hashes`.
There are no SonarQube exceptions for source installation.

Commands after installation use `uv run --no-sync --no-build` to avoid implicit
dependency resynchronization. The first-party project itself is still built
from the reviewed checkout, including during the container build.

Native macOS jobs additionally enforce Apple's `swift format` lint before
running the native tests. GitHub workflow syntax is validated in CI with
Actionlint 1.7.12, whose release archive is SHA-256 verified. Configuration tests ensure actions remain pinned,
scanner failures remain blocking, and quality/security checks gate publication.

Quality and repository security jobs start independently of the platform test
matrix. Images and downloads are published only after these checks, all platform
tests, image scans and real-container acceptance have passed. A runner allocation
failure is a failed gate and is retried, never treated as a successful test.

The public repository is connected to [SonarQube Cloud](https://sonarcloud.io/project/overview?id=ricardomartins-gravitee_openmaskit-companion)
on the free OSS plan. Its GitHub App runs automatic analysis on the default
branch and active pull requests. This hosted analysis is separate from the
blocking quality/security workflow above and does not import coverage reports.
See [SonarQube setup](sonarqube.md) for details.

Credentials are generated with Python's `secrets` module rather than a static
value or a predictable random generator. Scanners detect accidental disclosure;
they do not replace local credential generation or access controls.

## Local checks

Run Trivy 0.70.0 against a clean checkout or a tracked-tree export:

```sh
trivy repo --scanners vuln,misconfig,secret \
  --severity HIGH,CRITICAL --exit-code 1 \
  --format json --output /tmp/trivy-report.json .
```

The report can contain sensitive source excerpts from secret findings. Keep it
private and remove it after review. The CI job keeps its report on an ephemeral
runner and does not publish it.

Run Gitleaks 8.30.1 over all available repository history:

```sh
gitleaks git --redact=100 --report-format=json \
  --report-path /tmp/gitleaks-report.json --no-banner .
```

Gitleaks redacts secrets in its logs and report. Full history is required; a
shallow clone cannot provide the same check. Rotate and remove any confirmed
credential, rather than treating an ignore entry as remediation.

## Current baseline scan

On the current tracked tree, Trivy 0.70.0 reported no HIGH or CRITICAL
vulnerabilities, misconfigurations, or secrets. The Gitleaks 8.30.1 full-history
scan found no secrets. The Starlette dependency was updated to a patched
version; no finding was suppressed to reach this result.

There are currently no Trivy or Gitleaks exceptions. If a future finding is confirmed as
a false positive, add only a rule-specific exception for the affected file or
resource and document the evidence and review date here. Do not disable a
scanner, severity, or directory class to make a check green.

The older Debian Python base inherited unfixed OS vulnerabilities. The companion
now uses the official Python 3.12.15 Alpine image, pinned by its multi-architecture
digest in both builder and runtime stages. The rebuilt complete companion image
passed its HIGH/CRITICAL vulnerability and secret scan, and the real OpenMaskit +
Presidio acceptance test passed on that image. This result describes the companion
image; separately maintained OpenMaskit and Presidio images have their own release
and dependency lifecycle.

## Pinned upstream sources

- [Trivy Action v0.36.0 release](https://github.com/aquasecurity/trivy-action/releases/tag/v0.36.0)
- [Trivy repository scanning documentation](https://trivy.dev/docs/latest/target/repository/)
- [Gitleaks v8.30.1 release](https://github.com/gitleaks/gitleaks/releases/tag/v8.30.1)
- [Gitleaks CLI documentation](https://github.com/gitleaks/gitleaks)
- [actions/checkout v7.0.1 release](https://github.com/actions/checkout/releases/tag/v7.0.1)
