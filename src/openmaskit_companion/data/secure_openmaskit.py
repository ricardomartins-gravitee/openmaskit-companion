"""Container entrypoint: extend this app's CA bundle, then run OpenMaskit."""

import os
import tempfile
from pathlib import Path

import certifi


def run():
    trusted = Path("/opt/openmaskit-relay/ca.pem").read_bytes()
    descriptor, path = tempfile.mkstemp(prefix="openmaskit-relay-ca-", suffix=".pem")
    with os.fdopen(descriptor, "wb") as output:
        output.write(Path(certifi.where()).read_bytes() + b"\n" + trusted)
    os.environ["SSL_CERT_FILE"] = path
    from openmaskit.__main__ import main

    main()


if __name__ == "__main__":
    run()
