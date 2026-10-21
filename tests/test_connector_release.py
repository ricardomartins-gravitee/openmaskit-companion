import hashlib
import importlib.util
import io
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "connector_release", ROOT / "scripts/connector_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
PIN = {
    "repository": release.REPOSITORY,
    "version": "0.1.0a1",
    "protocol": 1,
    "commit": "a" * 40,
}


def metadata():
    return {
        "schema": 1,
        "version": PIN["version"],
        "protocol": 1,
        "commit": PIN["commit"],
        "relay_image": release.IMAGE_PREFIX + "b" * 64,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", 2),
        ("protocol", 2),
        ("commit", "c" * 40),
        ("version", "0.2.0"),
        ("relay_image", "example/image:latest"),
        ("relay_image", release.IMAGE_PREFIX + "x" * 64),
    ],
)
def test_release_rejects_wrong_source_protocol_and_mutable_images(field, value):
    data = metadata()
    data[field] = value
    with pytest.raises(ValueError):
        release.validate_metadata(data, PIN)


def mock_download(monkeypatch):
    data = metadata()
    content = json.dumps(data).encode()
    tag = "connector-v" + PIN["version"]
    asset = {
        "name": "connector-release.json",
        "size": len(content),
        "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
        "browser_download_url": f"https://github.com/{release.REPOSITORY}/releases/download/{tag}/connector-release.json",
    }
    record = {"tag_name": tag, "draft": False, "assets": [asset]}

    class Opener:
        def open(self, request, timeout):
            assert timeout == 60
            return io.BytesIO(
                json.dumps(record).encode() if hasattr(request, "full_url") else content
            )

    monkeypatch.setattr(release.urllib.request, "build_opener", lambda *args: Opener())
    return data, record


def test_release_requires_exact_main_workflow_provenance(tmp_path, monkeypatch):
    data, _ = mock_download(monkeypatch)
    calls = []
    monkeypatch.setattr(
        release.subprocess, "run", lambda args, **kw: calls.append((args, kw))
    )
    assert release.release_metadata(PIN, tmp_path) == data["relay_image"]
    args, options = calls[0]
    assert args[:3] == ["gh", "attestation", "verify"]
    assert args[args.index("--source-digest") + 1] == PIN["commit"]
    assert args[args.index("--source-ref") + 1] == "refs/heads/main"
    assert (
        args[args.index("--signer-workflow") + 1]
        == f"{release.REPOSITORY}/.github/workflows/validate.yml"
    )
    assert "--deny-self-hosted-runners" in args
    assert options == {"check": True, "timeout": 180}


def test_bad_attestation_never_accepts_release(tmp_path, monkeypatch):
    mock_download(monkeypatch)

    def reject(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(release.subprocess, "run", reject)
    with pytest.raises(subprocess.CalledProcessError):
        release.release_metadata(PIN, tmp_path)


@pytest.mark.parametrize("failure", ["digest", "missing", "size", "url", "draft"])
def test_invalid_asset_rejected_before_attestation(tmp_path, monkeypatch, failure):
    _, record = mock_download(monkeypatch)
    if failure == "draft":
        record["draft"] = True
    elif failure == "missing":
        record["assets"] = []
    else:
        field, value = {
            "digest": ("digest", "sha256:" + "0" * 64),
            "size": ("size", 1),
            "url": ("browser_download_url", "https://evil.example/metadata"),
        }[failure]
        record["assets"][0][field] = value
    monkeypatch.setattr(
        release.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("Invalid asset must be rejected first"),
    )
    with pytest.raises(ValueError):
        release.release_metadata(PIN, tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("repository", "other/repo"),
        ("commit", "main"),
        ("version", "../escape"),
        ("protocol", 2),
    ],
)
def test_invalid_reviewed_pin_rejected_before_network(field, value):
    pin = {**PIN, field: value}
    with pytest.raises(ValueError):
        release.validate_pin(pin)
