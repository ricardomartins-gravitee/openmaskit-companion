# Intel macOS dependency consumption

Intel cryptography wheel builds and durable native dependency releases are
owned by the [OpenMaskit Connector repository](https://github.com/ricardomartins-gravitee/openmaskit-connector).
The companion does not duplicate or publish that build. Its dependency lock
pins the connector source to a full immutable Git revision.

Companion CI uses the connector-owned helper and verification path at the
pinned revision to obtain and verify the Intel wheel for the app bundle. It
must check the artifact's provenance, source/build manifest, native build key,
wheel metadata and checksums before installation. The same verified
workflow-run artifact is used for downstream Intel checks and packaging. No
companion build step may silently source-build cryptography as a fallback or
compile dependencies on a user's Mac.

The connector's [Intel dependency build documentation](https://github.com/ricardomartins-gravitee/openmaskit-connector/blob/main/docs/intel-wheel.md)
describes the pinned cryptography and OpenSSL inputs, build recipe, scans,
durable release policy and bootstrap dependency. Native dependency artifacts
should be treated as available only after their provenance and hashes have
been verified; this document does not claim that a new connector release has
already been published.
