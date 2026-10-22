"""The production app resolves and uses the immutable native design dependency."""

import importlib.util
import json
import plistlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "desktop/macos"


def test_design_dependency_is_immutable_and_resolution_matches():
    manifest = (MAC / "Package.swift").read_text()
    revision = re.search(
        r'openmaskit-design-system.git",\s*revision: "([0-9a-f]{40})"', manifest
    )[1]
    pins = json.loads((MAC / "Package.resolved").read_text())["pins"]
    design = [pin for pin in pins if pin["identity"] == "openmaskit-design-system"]
    assert len(design) == 1
    assert design[0]["state"]["revision"] == revision
    assert (
        design[0]["location"]
        == "https://github.com/ricardomartins-gravitee/openmaskit-design-system.git"
    )
    assert (
        '.product(name: "OpenMaskitDesign", package: "openmaskit-design-system")'
        in manifest
    )


def test_production_views_use_shared_native_components_and_semantic_values():
    appearance = (MAC / "Sources/OpenMaskitCompanion/Appearance.swift").read_text()
    assert "import OpenMaskitDesign" in appearance
    for alias in [
        "CompanionTheme = OpenMaskitTheme",
        "CompanionButtonStyle = OpenMaskitButtonStyle",
        "CompanionBadge = OpenMaskitBadge",
        "= OpenMaskitPanel<Content>",
    ]:
        assert alias in appearance
    assert "0x" not in appearance
    assert "struct CompanionButtonStyle" not in appearance
    assert "struct CompanionBrandIcon" in appearance
    for name in ["Overview.swift", "Settings.swift"]:
        source = (MAC / "Sources/OpenMaskitCompanion" / name).read_text()
        assert "CompanionTokens.spaceLg" in source
        assert "CompanionTypography.body" in source
        assert "CompanionPanel(" in source
        assert "WebView" not in source


def test_native_window_and_menu_lifecycle_stays_owned_by_the_app():
    app = (MAC / "Sources/OpenMaskitCompanion/App.swift").read_text()
    settings = (MAC / "Sources/OpenMaskitCompanion/Settings.swift").read_text()
    windows = (MAC / "Sources/OpenMaskitCompanion/Windows.swift").read_text()
    assert 'MenuBarExtra("OpenMaskit Companion", systemImage: "link")' in app
    assert "isInserted:" not in app
    assert "showInMenuBar" not in settings
    assert "closeToMenuBar" not in settings
    assert "Menu bar & window" not in settings
    assert "AppPreferences" in app
    assert "NSWindowDelegate" in windows
    assert "preferences.windowClosed()" in windows
    assert 'keyboardShortcut("q")' in settings
    assert 'Window("OpenMaskit Companion"' not in app
    assert "model.startMonitoring(preferences: preferences)" in app
    assert 'Button("Start All")' in settings and 'Button("Stop All")' in settings
    assert "init() { CompanionInstance.enforce() }" in app
    assert "reopenRunningApp" in app
    assert "private var settings: CompanionWindow?" in app
    assert "private var onboarding: CompanionWindow?" in app


def test_app_identity_stays_single_instance_and_menu_first(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "identity_bundle", ROOT / "scripts/bundle.py"
    )
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    bundle.write_info_plist(tmp_path)
    with (tmp_path / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    assert info["CFBundleName"] == "OpenMaskit Companion"
    assert (
        info["CFBundleIdentifier"]
        == "io.github.ricardomartins-gravitee.openmaskit-companion"
    )
    assert info["LSMultipleInstancesProhibited"] is True
    assert info["LSUIElement"] is True


def test_app_bundle_preserves_shared_library_attribution(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "design_bundle", ROOT / "scripts/bundle.py"
    )
    bundle = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundle)
    monkeypatch.setattr(bundle, "ROOT", tmp_path)
    checkout = tmp_path / "desktop/macos/.build/checkouts/openmaskit-design-system"
    checkout.mkdir(parents=True)
    notices = {
        "LICENSE": "Apache-2.0 fixture",
        "NOTICE": "Synthetic upstream attribution",
        "TRADEMARKS.md": "Synthetic trademark notice",
    }
    for name, text in notices.items():
        (checkout / name).write_text(text)
        (checkout / name).chmod(0o444)
    resources = tmp_path / "Contents/Resources"
    resources.mkdir(parents=True)
    bundle.copy_design_notices(resources)
    for name, text in notices.items():
        assert (resources / "ThirdParty/OpenMaskitDesign" / name).read_text() == text
        # Exercise a rebuild over read-only notices produced by older bundles.
        (resources / "ThirdParty/OpenMaskitDesign" / name).chmod(0o444)
    bundle.copy_design_notices(resources)
    for name, text in notices.items():
        output = resources / "ThirdParty/OpenMaskitDesign" / name
        assert output.read_text() == text
        assert output.stat().st_mode & 0o200
    assert "copy_design_notices(resources)" in (ROOT / "scripts/bundle.py").read_text()
