import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_helper(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "install_connector", ROOT / "scripts/install_connector.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_wheel(
    directory,
    *,
    version="0.1.0a3",
    tag="py3-none-any",
    native=False,
    metadata_name="openmaskit-connector",
):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"openmaskit_connector-{version}-{tag}.whl"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr(
            f"openmaskit_connector-{version}.dist-info/METADATA",
            f"Name: {metadata_name}\nVersion: {version}\n",
        )
        if native:
            package.writestr("unreviewed.so", b"native")
    return path


def pin():
    return json.loads((ROOT / "dependencies/connector.json").read_text())


@pytest.mark.parametrize("change", ["version", "tag", "metadata", "native"])
def test_only_reviewed_pure_python_package_is_accepted(tmp_path, monkeypatch, change):
    helper = load_helper(monkeypatch)
    options = {
        "version": {"version": "0.2.0"},
        "tag": {"tag": "cp312-cp312-macosx_14_0_arm64"},
        "metadata": {"metadata_name": "other-project"},
        "native": {"native": True},
    }[change]
    make_wheel(tmp_path, **options)
    with pytest.raises(ValueError):
        helper.verify_wheel(tmp_path, pin())


def test_wrong_source_commit_never_builds_or_installs(tmp_path, monkeypatch):
    helper = load_helper(monkeypatch)
    monkeypatch.setattr(helper.subprocess, "check_output", lambda *a, **kw: "0" * 40)
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("Wrong checkout must never execute"),
    )
    with pytest.raises(ValueError, match="immutable"):
        helper.install(pin(), tmp_path)


def test_exact_source_is_packaged_then_installed_with_hashes(tmp_path, monkeypatch):
    helper = load_helper(monkeypatch)
    monkeypatch.setattr(helper, "ROOT", tmp_path)
    monkeypatch.setattr(
        helper.subprocess,
        "check_output",
        lambda args, **kw: "" if "status" in args else pin()["commit"],
    )
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        assert kwargs == {"check": True, "timeout": 180}
        if args[:2] == ["uv", "build"]:
            assert args[2] == str(tmp_path / ".runtime/connector-source")
            assert "--no-build-isolation" in args and "--no-sources" in args
            make_wheel(Path(args[args.index("--out-dir") + 1]))
        else:
            assert args[:3] == ["uv", "pip", "install"]
            assert all(
                value in args
                for value in ["--no-deps", "--no-build", "--require-hashes"]
            )
            requirements = Path(args[args.index("--requirement") + 1]).read_text()
            assert (
                requirements.startswith("file:///") and "--hash=sha256:" in requirements
            )

    monkeypatch.setattr(helper.subprocess, "run", run)
    helper.install(pin(), tmp_path)
    assert len(calls) == 2


def test_dirty_checkout_is_rejected_before_packaging(tmp_path, monkeypatch):
    helper = load_helper(monkeypatch)
    monkeypatch.setattr(
        helper.subprocess,
        "check_output",
        lambda args, **kw: (
            " M src/modified.py" if "status" in args else pin()["commit"]
        ),
    )
    monkeypatch.setattr(
        helper.subprocess,
        "run",
        lambda *a, **kw: pytest.fail("Dirty checkout must never execute"),
    )
    with pytest.raises(ValueError, match="clean"):
        helper.install(pin(), tmp_path)
