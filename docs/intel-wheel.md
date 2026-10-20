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
3. Scan the extracted upstream dependency lockfiles with Trivy.
   HIGH/CRITICAL vulnerabilities block the job. This additional dependency check
   does not apply credential rules to upstream documentation examples containing
   published test private keys. Our repository/history and final image have
   their own blocking secret scans.
4. Download OpenSSL 3.5.9 LTS from its official GitHub release, using the source
   URL, size and SHA-256 in `dependencies/openssl.json`. Allow redirects only to
   GitHub's HTTPS release asset host and verify the source before extraction.
   Compile static libraries for Intel macOS 14+, run the full upstream OpenSSL
   test suite, and install only into the job's temporary directory. Build
   cryptography with `uv build --no-build-isolation`, using the already installed
   Python build tools and that private static OpenSSL installation. These two
   explicit compilation steps never use the runner's Homebrew OpenSSL.
5. Require one Intel macOS wheel with the exact locked package name/version in
   both its filename and embedded metadata. Record the Git commit, source hash
   and built wheel hash in a manifest, together with OpenSSL's version/source hash.
6. Install only that checksummed wheel, with dependency resolution and source
   builds disabled. Test AES-GCM against a known vector, Fernet encryption,
   Ed25519/RSA signing and PEM loading, plus rejection of tampered inputs.
   Inspect the Mach-O links: only system libraries are allowed as dependencies,
   so a download does not depend on the CI runner's Homebrew paths.
7. Read the actual embedded OpenSSL version from the native module and generate
   a small CycloneDX SBOM, requiring that version to match the pinned LTS release.
   Trivy checks the Python package. Grype checks the
   explicit OpenSSL CPE, since Trivy does not recognize its generic package URL.
   Both checks fail on HIGH/CRITICAL findings, including unfixed findings. Scan
   errors fail the job. No findings are dismissed to permit publication.
8. Upload the wheel, manifest, SBOM and toolchain inventory as a same-run GitHub
   artifact. Intel tests and Intel packaging download that exact artifact,
   verify it against their checkout and install it with required SHA-256 hashes.
   They repeat native cryptographic checks before the normal downstream tests
   or bundle acceptance. No step falls back to compiling at installation time.
   The pull request also builds the Intel development app and exercises the
   packaged executable through the real bidirectional MCP integration tests.

## Maintenance and limits

Python build inputs, upstream Rust dependencies and OpenSSL source are locked.
The Xcode/Rust toolchains follow the GitHub runner image; their versions are
recorded in the artifact. This is not a claim of bit-for-bit reproducibility
across different runner images. The OpenSSL scan uses the version actually
linked and rejects accidental linkage to an unpinned runner library.

The SBOM describes cryptography and its embedded OpenSSL. It is not a complete
SBOM for the app or a substitute for the separate runtime/build dependency audit,
upstream Rust scan, repository scans and final container scans. Static linking
requires a rebuild to deliver OpenSSL fixes; every workflow run creates a fresh
wheel and reruns the checks. There is no scheduled local task or local updater.
OpenSSL source updates require a reviewed change to `dependencies/openssl.json`;
the dependency scans block a release when the pinned version acquires a known
HIGH/CRITICAL advisory. The 3.5 LTS series is maintained until April 2030; its
current releases and lifecycle are listed on the
[official download page](https://openssl-library.org/source/).

If a future cryptography update changes the backend requirements, removes its
Cargo lockfile, changes its version format or produces a different platform tag,
the build fails for review. If upstream restores compatible Intel wheels, this
additional build can be removed and Intel can use the normal binary installation.

The current source-build recipe follows the upstream
[cryptography macOS build documentation](https://cryptography.io/en/latest/installation/#building-cryptography-on-macos).
