# Native dependency ownership

The reusable Intel macOS cryptography wheel and its statically linked OpenSSL
are built, scanned, attested and published by the
[OpenMaskit Connector repository](https://github.com/ricardomartins-gravitee/openmaskit-connector).
They are connector build dependencies, not companion application releases or
upstream cryptography/OpenSSL releases.

Companion CI uses the connector-owned helper and verification path pinned by
the connector source revision in `uv.lock`. Before the app bundle consumes the
wheel, CI verifies its provenance, build inputs, metadata and checksums. No
native dependency release is assumed available until those checks pass.

See the connector's [Intel dependency build](https://github.com/ricardomartins-gravitee/openmaskit-connector/blob/main/docs/intel-wheel.md)
and [native dependency release policy](https://github.com/ricardomartins-gravitee/openmaskit-connector/blob/main/docs/native-dependency-release.md)
for build and publication details.
