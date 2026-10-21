import ssl
from importlib.resources import files

import pytest
import yaml
from cryptography import x509
from openmaskit_connector.state import write_json

from openmaskit_companion import relay_tls


def test_certificates_are_separate_private_and_idempotent(tmp_path):
    relay_tls.provision(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    relay_tls.provision(tmp_path)
    assert {p: p.read_bytes() for p in before} == before
    folder = tmp_path / "stack/tls"
    assert (folder / "relay.key").stat().st_mode & 0o777 == 0o600
    ca_key = tmp_path / "tls-authority/ca.key"
    assert ca_key.stat().st_mode & 0o777 == 0o600
    assert ca_key.read_bytes() != (folder / "relay.key").read_bytes()
    ca = x509.load_pem_x509_certificate((folder / "ca.pem").read_bytes())
    server = x509.load_pem_x509_certificate((folder / "relay.pem").read_bytes())
    server.verify_directly_issued_by(ca)
    names = server.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert "connector-relay" in names.get_values_for_type(x509.DNSName)
    assert "localhost" in names.get_values_for_type(x509.DNSName)
    context = relay_tls.client_context(tmp_path)
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_provision_never_overwrites_interrupted_or_existing_material(tmp_path):
    folder = tmp_path / "stack/tls"
    folder.mkdir(parents=True)
    file = folder / "relay.key"
    file.write_bytes(b"synthetic existing key")
    with pytest.raises(ValueError, match="Incomplete"):
        relay_tls.provision(tmp_path)
    assert file.read_bytes() == b"synthetic existing key"


def test_wrong_ca_mismatched_key_public_key_and_symlinks_fail_closed(tmp_path):
    home = tmp_path / "first"
    other = tmp_path / "other"
    relay_tls.provision(home)
    relay_tls.provision(other)
    ca_file = home / "stack/tls/ca.pem"
    original = ca_file.read_bytes()
    ca_file.write_bytes((other / "stack/tls/ca.pem").read_bytes())
    with pytest.raises(ValueError):
        relay_tls.validate(home)
    ca_file.write_bytes(original)
    key = home / "stack/tls/relay.key"
    original = key.read_bytes()
    key.write_bytes((other / "stack/tls/relay.key").read_bytes())
    with pytest.raises(ssl.SSLError):
        relay_tls.validate(home)
    key.write_bytes(original)
    key.chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        relay_tls.validate(home)
    key.chmod(0o600)
    key.unlink()
    key.symlink_to(other / "stack/tls/relay.key")
    with pytest.raises(ValueError, match="unavailable"):
        relay_tls.validate(home)


def test_invalid_marker_does_not_replace_anything(tmp_path):
    relay_tls.provision(tmp_path)
    write_json(tmp_path / "stack/tls.json", {"schema": 2})
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        relay_tls.provision(tmp_path)
    assert {p: p.read_bytes() for p in before} == before


def test_stack_tls_preserves_images_project_volume_ports_and_custom_settings(tmp_path):
    text = files("openmaskit_companion").joinpath("data/compose.yaml").read_text()
    before = yaml.safe_load(text)
    before["services"]["openmaskit"]["environment"]["CUSTOM_SETTING"] = "synthetic-kept"
    before["services"]["openmaskit"]["mem_limit"] = "512m"
    after = yaml.safe_load(relay_tls.compose_with_tls(yaml.safe_dump(before)))
    for key in ("name", "volumes", "networks"):
        assert after[key] == before[key]
    for name in before["services"]:
        for key in (
            "ports",
            "image",
            "user",
            "networks",
            "restart",
            "environment",
            "mem_limit",
        ):
            assert after["services"][name].get(key) == before["services"][name].get(key)
    assert (
        after["services"]["presidio-analyzer"]
        == before["services"]["presidio-analyzer"]
    )
    assert after["services"]["connector-relay"]["command"][-4:] == [
        "--tls-cert",
        "/tls/relay.pem",
        "--tls-key",
        "/tls/relay.key",
    ]
    assert not any(
        "ca.key" in str(v)
        for service in after["services"].values()
        for v in service.get("volumes", [])
    )
    stack = tmp_path / "stack"
    stack.mkdir()
    (stack / "compose.yaml").write_text(text)
    relay_tls.prepare_stack(tmp_path)
    snapshot = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    relay_tls.prepare_stack(tmp_path)
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in snapshot} == snapshot


def test_custom_entrypoint_or_colliding_mount_is_not_overwritten():
    config = yaml.safe_load(
        files("openmaskit_companion").joinpath("data/compose.yaml").read_text()
    )
    config["services"]["openmaskit"]["entrypoint"] = ["custom-command"]
    with pytest.raises(ValueError, match="custom OpenMaskit entrypoint"):
        relay_tls.compose_with_tls(yaml.safe_dump(config))
    del config["services"]["openmaskit"]["entrypoint"]
    config["services"]["openmaskit"]["volumes"].append(
        "./unrelated:/opt/openmaskit-relay/ca.pem:ro"
    )
    with pytest.raises(ValueError, match="replace an existing volume"):
        relay_tls.compose_with_tls(yaml.safe_dump(config))
