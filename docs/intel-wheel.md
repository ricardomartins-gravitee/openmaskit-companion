# Intel macOS dependency build

Both Apple Silicon and Intel macOS remain supported. The locked cryptography
release currently has no Intel macOS wheel on PyPI. The app must therefore ship
our own Intel binary; users of a packaged app do not need Rust, Xcode or Homebrew
to compile this dependency.

`.github/workflows/intel-wheel.yml` builds a fresh wheel for each validation run,
after the repository quality and security jobs pass. It has read-only repository
permissions, no repository secrets, and no persistent compiler cache. It never
downloads an executable artifact from another workflow or a previous PR run.

## Build and acceptance

1. Install only the `intel-build` group from `uv.lock`, with `--frozen --no-build`.
   This includes binary wheels for Maturin, CFFI, setuptools and packaging.
2. Download cryptography's exact locked source from PyPI's HTTPS file host.
   Refuse redirects; verify its size and SHA-256 before extracting or building.
   Extraction uses Python's safe data filter. Require the upstream Cargo lockfile
   and Maturin's `locked = true` setting, preventing Rust dependency re-resolution.
3. Scan the extracted upstream source and Cargo dependencies with Trivy.
   HIGH/CRITICAL vulnerabilities and detected secrets block the job.
4. Explicitly build that verified source with `uv build --no-build-isolation`,
   using the already installed Python build tools. This is the only third-party
   compilation step. macOS deployment target is 14.0 and OpenSSL is statically
   linked from the hosted runner's Homebrew installation.
5. Require one Intel macOS wheel with the exact locked package name/version in
   both its filename and embedded metadata. Record the Git commit, source hash
   and built wheel hash in a manifest.
6. Install only that checksummed wheel, with dependency resolution and source
   builds disabled. Test AES-GCM against a known vector, Fernet encryption,
   Ed25519/RSA signing and PEM loading, plus rejection of tampered inputs.
   Inspect the Mach-O links: only system libraries are allowed as dependencies,
   so a download does not depend on the CI runner's Homebrew paths.
7. Read the actual embedded OpenSSL version from the native module and generate
   a small CycloneDX SBOM. Trivy checks the Python package. Grype checks the
   explicit OpenSSL CPE, since Trivy does not recognize its generic package URL.
   Both checks fail on HIGH/CRITICAL findings, including unfixed findings. Scan
   errors fail the job. No findings are dismissed to permit publication.
8. Upload the wheel, manifest, SBOM and toolchain inventory as a same-run GitHub
   artifact. Intel tests and Intel packaging download that exact artifact,
   verify it against their checkout and install it with required SHA-256 hashes.
   They repeat native cryptographic checks before the normal downstream tests
   or bundle acceptance. No step falls back to compiling at installation time.

## Maintenance and limits

Python build inputs and upstream Rust dependencies are locked. The Xcode/Rust
toolchains and Homebrew OpenSSL follow the GitHub runner image; their versions
are recorded in the artifact. This is not a claim of bit-for-bit reproducibility
across different runner images. The OpenSSL scan uses the version actually
linked, rather than assuming the Homebrew formula version matches the binary.

The SBOM describes cryptography and its embedded OpenSSL. It is not a complete
SBOM for the app or a substitute for the separate runtime/build dependency audit,
upstream Rust scan, repository scans and final container scans. Static linking
requires a rebuild to deliver OpenSSL fixes; every workflow run creates a fresh
wheel and reruns the checks. There is no scheduled local task or local updater.

If a future cryptography update changes the backend requirements, removes its
Cargo lockfile, changes its version format or produces a different platform tag,
the build fails for review. If upstream restores compatible Intel wheels, this
additional build can be removed and Intel can use the normal binary installation.

The current source-build recipe follows the upstream
[cryptography macOS build documentation](https://cryptography.io/en/latest/installation/#building-cryptography-on-macos).
