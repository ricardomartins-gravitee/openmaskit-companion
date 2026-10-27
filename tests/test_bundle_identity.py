"""Exercise actual macOS code signatures, including the original CLI-wrapper flaw."""

import importlib.util
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "identity_bundle", ROOT / "scripts/bundle.py"
)
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="Uses macOS codesign and Swift"
)


@pytest.fixture(scope="module")
def native_executable(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-bundle-identity")
    source = root / "main.swift"
    source.write_text('print("synthetic bundle identity acceptance")\n')
    executable = root / "OpenMaskitCompanion"
    subprocess.run(
        ["swiftc", str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return executable


@pytest.fixture
def app(tmp_path, native_executable):
    app = tmp_path / "OpenMaskit Companion.app"
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    shutil.copy2(native_executable, contents / "MacOS/OpenMaskitCompanion")
    (contents / "Resources/synthetic.txt").write_text("synthetic sealed resource")
    bundle.write_info_plist(contents)
    return app


def test_linker_signature_is_rejected_until_the_complete_bundle_is_signed(app):
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        bundle.verify_development_bundle(app)
    bundle.sign_development_bundle(app)
    bundle.verify_development_bundle(app)


@pytest.mark.parametrize("changed", ["metadata", "resource", "signing_identifier"])
def test_modified_identity_metadata_or_resources_are_rejected(app, changed):
    bundle.sign_development_bundle(app)
    if changed == "metadata":
        path = app / "Contents/Info.plist"
        info = plistlib.loads(path.read_bytes())
        info["CFBundleName"] = "Synthetic changed metadata"
        path.write_bytes(plistlib.dumps(info))
    elif changed == "resource":
        (app / "Contents/Resources/synthetic.txt").write_text(
            "synthetic changed resource"
        )
    else:
        subprocess.run(
            [
                "/usr/bin/codesign",
                "--force",
                "--sign",
                "-",
                "--identifier",
                "synthetic.wrong",
                str(app),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        bundle.verify_development_bundle(app)


def archive_module(monkeypatch, app, root):
    monkeypatch.setitem(sys.modules, "bundle", bundle)
    spec = importlib.util.spec_from_file_location(
        "identity_archive", ROOT / "scripts/archive.py"
    )
    archive = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(archive)
    monkeypatch.setattr(archive, "ROOT", root)
    monkeypatch.setattr(archive, "APP", app)
    return archive


@pytest.mark.parametrize("changed", ["unbound", "tampered"])
def test_archiving_rejects_unbound_or_tampered_apps_before_creating_downloads(
    app, tmp_path, monkeypatch, changed
):
    if changed == "tampered":
        bundle.sign_development_bundle(app)
        (app / "Contents/Resources/synthetic.txt").write_text("changed after signing")
    archive = archive_module(monkeypatch, app, tmp_path)
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        archive.main()
    assert not (tmp_path / "dist/downloads").exists()


def test_archiving_and_extraction_preserve_the_verified_bundle_signature(
    app, tmp_path, monkeypatch
):
    bundle.sign_development_bundle(app)
    archive = archive_module(monkeypatch, app, tmp_path)
    archive.main()
    downloads = tmp_path / "dist/downloads"
    archives = list(downloads.glob("*.zip"))
    assert len(archives) == 1
    extracted = tmp_path / "extracted"
    subprocess.run(
        ["/usr/bin/ditto", "-x", "-k", str(archives[0]), str(extracted)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    bundle.verify_development_bundle(extracted / app.name)
