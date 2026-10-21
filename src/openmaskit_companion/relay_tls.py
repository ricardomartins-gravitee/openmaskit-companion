"""Provision private relay certificates without installing a system trust root."""

from __future__ import annotations

import os
import ssl
import tempfile
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from ipaddress import ip_address
from pathlib import Path

import yaml
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from openmaskit_connector.state import private_dir, read_json, write_json


def _write(path, data, mode):
    if path.exists() or path.is_symlink():
        raise ValueError("TLS provisioning will not overwrite existing files")
    descriptor, temporary = tempfile.mkstemp(prefix=".tls-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), mode)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _key_bytes(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def provision(home: Path):
    """Idempotently create a local CA and a separate relay server key/cert.

    The CA private key is host-only. Containers receive only the relay key or
    the public CA certificate they need. Existing material is never rotated by
    app startup or overwritten on an interrupted provisioning attempt.
    """
    private_dir(home)
    if (home / "stack").is_symlink():
        raise ValueError("TLS directories cannot be symbolic links")
    marker = home / "stack/tls.json"
    public = private_dir(home / "stack/tls")
    authority = private_dir(home / "tls-authority")
    if marker.exists():
        validate(home)
        return
    if any(public.iterdir()) or any(authority.iterdir()):
        raise ValueError("Incomplete TLS provisioning requires backup and repair")
    now = datetime.now(timezone.utc)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "OpenMaskit local relay CA")]
    )
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    server = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "connector-relay")])
        )
        .issuer_name(ca.subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("connector-relay"),
                    x509.DNSName("localhost"),
                    x509.IPAddress(ip_address("127.0.0.1")),
                    x509.IPAddress(ip_address("::1")),
                ]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    _write(authority / "ca.key", _key_bytes(ca_key), 0o600)
    _write(public / "ca.pem", ca.public_bytes(serialization.Encoding.PEM), 0o644)
    _write(public / "relay.pem", server.public_bytes(serialization.Encoding.PEM), 0o644)
    _write(public / "relay.key", _key_bytes(server_key), 0o600)
    write_json(marker, {"schema": 1, "transport": "verified-tls"})
    validate(home)


def validate(home: Path):
    if home.is_symlink() or (home / "stack").is_symlink():
        raise ValueError("TLS directories cannot be symbolic links")
    if read_json(home / "stack/tls.json") != {"schema": 1, "transport": "verified-tls"}:
        raise ValueError("A verified relay TLS installation is required")
    folder = home / "stack/tls"
    if folder.is_symlink():
        raise ValueError("TLS files cannot be symbolic links")
    for name in ("ca.pem", "relay.pem", "relay.key"):
        file = folder / name
        if file.is_symlink() or not file.is_file() or file.stat().st_size > 131_072:
            raise ValueError("TLS certificate files are unavailable")
    if os.name != "nt" and (folder / "relay.key").stat().st_mode & 0o077:
        raise ValueError("Relay private key permissions must be 0600")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(folder / "relay.pem", folder / "relay.key")
    certificates = [
        x509.load_pem_x509_certificate((folder / name).read_bytes())
        for name in ("ca.pem", "relay.pem")
    ]
    try:
        certificates[0].verify_directly_issued_by(certificates[0])
        certificates[1].verify_directly_issued_by(certificates[0])
    except InvalidSignature:
        raise ValueError("Relay certificate does not match its local CA") from None
    for certificate in certificates:
        if (
            not certificate.not_valid_before_utc
            <= datetime.now(timezone.utc)
            < certificate.not_valid_after_utc
        ):
            raise ValueError("Local relay certificate renewal is required")


def client_context(home: Path):
    validate(home)
    context = ssl.create_default_context(cafile=home / "stack/tls/ca.pem")
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def compose_with_tls(text: str):
    """Change the relay transport without dropping unrelated Compose settings."""
    config = yaml.safe_load(text)
    services = config["services"]
    openmaskit = services["openmaskit"]
    relay = services["connector-relay"]
    entrypoint = ["python", "/opt/openmaskit-relay/start.py"]
    if openmaskit.get("entrypoint") not in (None, entrypoint):
        raise ValueError("Review the custom OpenMaskit entrypoint before a TLS upgrade")
    openmaskit["entrypoint"] = entrypoint

    def mount(service, source, destination):
        volumes = service.setdefault("volumes", [])
        expected = f"{source}:{destination}:ro"
        for volume in volumes:
            if isinstance(volume, str) and volume.split(":")[1:2] == [destination]:
                if volume != expected:
                    raise ValueError("TLS mount would replace an existing volume")
                return
            if isinstance(volume, dict) and volume.get("target") == destination:
                raise ValueError("TLS mount would replace an existing volume")
        volumes.append(expected)

    mount(openmaskit, "./tls/ca.pem", "/opt/openmaskit-relay/ca.pem")
    mount(openmaskit, "./secure_openmaskit.py", "/opt/openmaskit-relay/start.py")
    for name in ("relay.key", "relay.pem", "ca.pem"):
        mount(relay, "./tls/" + name, "/tls/" + name)
    command = relay.get("command")
    if not isinstance(command, list) or command[:1] != ["relay"]:
        raise ValueError("Review the custom relay command before a TLS upgrade")
    tls_arguments = ["--tls-cert", "/tls/relay.pem", "--tls-key", "/tls/relay.key"]
    if "--tls-cert" not in command and "--tls-key" not in command:
        relay["command"] = command + tls_arguments
    elif command[-4:] != tls_arguments:
        raise ValueError("Review the custom relay TLS settings before an upgrade")
    relay.setdefault("healthcheck", {})["test"] = [
        "CMD",
        "python",
        "-c",
        "import ssl,urllib.request; "
        "urllib.request.urlopen('https://127.0.0.1:9495/health',"
        "context=ssl.create_default_context(cafile='/tls/ca.pem'),timeout=5).close()",
    ]
    return yaml.safe_dump(config, sort_keys=False)


def validate_stack(home: Path):
    validate(home)
    path = home / "stack/compose.yaml"
    if path.is_symlink():
        raise ValueError("Managed Compose files cannot be symbolic links")
    text = path.read_text()
    if yaml.safe_load(text) != yaml.safe_load(compose_with_tls(text)):
        raise ValueError("The relay TLS upgrade is not complete")
    entry = home / "stack/secure_openmaskit.py"
    expected = (
        files("openmaskit_companion").joinpath("data/secure_openmaskit.py").read_bytes()
    )
    if entry.is_symlink() or entry.read_bytes() != expected:
        raise ValueError("The secure OpenMaskit entrypoint is unavailable")


def prepare_stack(home: Path):
    """Prepare files only; switching a running installation is a separate action."""
    compose = home / "stack/compose.yaml"
    if compose.is_symlink():
        raise ValueError("Managed Compose files cannot be symbolic links")
    previous = compose.read_text()
    updated = compose_with_tls(previous)
    provision(home)
    entry = home / "stack/secure_openmaskit.py"
    content = (
        files("openmaskit_companion").joinpath("data/secure_openmaskit.py").read_bytes()
    )
    if not entry.exists():
        _write(entry, content, 0o644)
    elif entry.is_symlink() or entry.read_bytes() != content:
        raise ValueError("Review the existing secure OpenMaskit entrypoint")
    if updated == previous:
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".compose-tls-", dir=compose.parent)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, compose)
    finally:
        Path(temporary).unlink(missing_ok=True)
