"""The production app resolves and uses the immutable native design dependency."""

import json
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
    assert "MenuBarExtra" in app
    assert "AppPreferences" in app
    assert "NSWindow.willCloseNotification" in settings
    assert "preferences?.windowClosed()" in settings
    assert 'keyboardShortcut("q")' in settings
