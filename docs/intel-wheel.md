# Intel macOS dependency build

Both Apple Silicon and Intel macOS remain supported. The locked cryptography
release currently has no Intel macOS wheel on PyPI. The app must therefore ship
our own Intel binary; users of a packaged app do not need Rust, Xcode or Homebrew
to compile this dependency.

`.github/workflows/intel-wheel.yml` reuses a matching stored wheel after the
repository quality and security jobs pass. It has read-only repository,
attestation and Actions access. Source compilation runs only when no matching
verified library is available.

## Durable reuse

The library is stored as a GitHub release asset under `native-intel-<build-key>`.
Release storage has no Actions artifact retention deadline or cache eviction.
The ZIP contains the wheel, original source/build manifest, component SBOM and
toolchain inventory. It is a dependency prerelease, not a new application release.

The SHA-256 build key includes the cryptography source, OpenSSL source,
transitive locked Python build tools, CPython/macOS/architecture target, uv
version and `scripts/build_intel_dependencies.sh`. App changes and unrelated
test-tool updates do not invalidate it. Changing native build inputs does.

Before extraction, a consumer verifies the release asset's checksum and GitHub
provenance. The signer must be this repository's `validate.yml`, with source ref
`refs/heads/main` and a GitHub-hosted runner. It then checks archive members,
uncompressed size, wheel metadata, source hashes, build key and wheel checksum.
The original build commit is retained across application revisions.

Only HTTP 404 means a release is absent and permits a source build. Network or
authorization errors, missing assets, bad hashes or invalid provenance fail
closed. A found but invalid stored library is never replaced by a silent build.

Only a main-branch job with all platform tests, image acceptance and security/
quality checks passing can attest and publish a new dependency release. PR jobs
cannot publish it. Publication is serialized by build key and never overwrites
an existing release asset. A verified existing release makes publication a no-op.

### Initial library

`dependencies/intel-bootstrap.json` pins the existing successful Intel build
from run 39465701552: its producer job, source revision, original build commit,
build key and exact wheel SHA-256. That job compiled pinned OpenSSL, passed its
full upstream suite, native cryptography checks and both component scans.
This narrowly scoped seed avoids repeating the build that just completed.
The loader verifies the successful producer and unexpired artifact, then checks
all source/metadata fields and the pinned wheel bytes before accepting it.
Any changed build key makes this seed ineligible. Other PR artifacts are not
accepted. Once the main job publishes the attested release, normal restoration
uses that release first; the seed file can then be removed in a reviewed change.

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
4. **On a miss only**, download OpenSSL 3.5.9 LTS from its official GitHub release, using the source
   URL, size and SHA-256 in `dependencies/openssl.json`. Allow redirects only to
   GitHub's HTTPS release asset host and verify the source before extraction.
   Compile static libraries for Intel macOS 14+, run the full upstream OpenSSL
   test suite, and install only into the job's temporary directory. Build
   cryptography with `uv build --no-build-isolation`, using the already installed
   Python build tools and that private static OpenSSL installation. These two
   explicit compilation steps never use the runner's Homebrew OpenSSL.
5. Require one Intel macOS wheel with the exact locked package name/version in
   both its filename and embedded metadata. Record the Git commit, source hash
   and built wheel hash in a manifest, together with OpenSSL's version/source hash
   and native build key. Restoration preserves the original build manifest.
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
   errors fail the job. These native checks and scans run on every use, including
   stored-library hits. No findings are dismissed to permit publication.
8. Upload the wheel, manifest, SBOM and toolchain inventory as a same-run GitHub
   artifact. Intel tests and Intel packaging download that exact artifact,
   verify it against their checkout and install it with required SHA-256 hashes.
   They repeat native cryptographic checks before the normal downstream tests
   or bundle acceptance. No step falls back to compiling at installation time.
   The pull request also builds the Intel development app and exercises the
   packaged executable through the real bidirectional MCP integration tests.

## Maintenance and limits

Python build inputs, upstream Rust dependencies and OpenSSL source are locked.
The original Xcode/Rust toolchain versions are recorded in the stored artifact.
A runner image update alone does not rebuild a compatible stored library.
Changing the reviewed build recipe deliberately invalidates it when a compiler
rebuild is needed. This is not a claim of bit-for-bit reproducibility
across different runner images. The OpenSSL scan uses the version actually
linked and rejects accidental linkage to an unpinned runner library.

The SBOM describes cryptography and its embedded OpenSSL. It is not a complete
SBOM for the app or a substitute for the separate runtime/build dependency audit,
upstream Rust scan, repository scans and final container scans. Static linking
requires a rebuild to deliver OpenSSL fixes. Updating its pinned source changes
the build key and causes one new source build, upstream test run and stored
release. Every consumer reruns vulnerability/native checks. There is no
scheduled local task or local updater.
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
