import importlib.util
import plistlib
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "desktop/macos/Assets"
SPEC = importlib.util.spec_from_file_location("bundle", ROOT / "scripts/bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


def test_app_icon_assets_have_expected_dimensions_and_icns_header():
    png = (ASSETS / "AppIcon.png").read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", png[16:24]) == (1024, 1024)
    assert png[25] == 6  # RGBA with alpha
    offset = 8
    image_data = bytearray()
    while offset < len(png):
        chunk_size = struct.unpack(">I", png[offset : offset + 4])[0]
        chunk_type = png[offset + 4 : offset + 8]
        if chunk_type == b"IDAT":
            image_data.extend(png[offset + 8 : offset + 8 + chunk_size])
        offset += 12 + chunk_size
    first_row = zlib.decompress(image_data)
    assert first_row[0] in range(5)  # PNG row filter
    assert first_row[4] == 0  # transparent top-left corner

    icns = (ASSETS / "AppIcon.icns").read_bytes()
    assert icns[:4] == b"icns"
    assert struct.unpack(">I", icns[4:8])[0] == len(icns)
    offset = 8
    embedded_png_sizes = set()
    while offset < len(icns):
        chunk_size = struct.unpack(">I", icns[offset + 4 : offset + 8])[0]
        payload = icns[offset + 8 : offset + chunk_size]
        if payload.startswith(b"\x89PNG\r\n\x1a\n"):
            embedded_png_sizes.add(struct.unpack(">II", payload[16:24]))
        offset += chunk_size
    assert offset == len(icns)
    assert {
        (32, 32),
        (64, 64),
        (128, 128),
        (256, 256),
        (512, 512),
        (1024, 1024),
    } <= embedded_png_sizes


def test_packaging_copies_both_app_icons_and_sets_icon_file(tmp_path):
    resources = tmp_path / "Contents/Resources"
    resources.mkdir(parents=True)
    app = resources.parent

    bundle.copy_app_icons(resources)
    bundle.write_info_plist(app)

    for name in ("AppIcon.png", "AppIcon.icns"):
        assert (resources / name).read_bytes() == (ASSETS / name).read_bytes()
    with (app / "Info.plist").open("rb") as source:
        info = plistlib.load(source)
    assert info["CFBundleIconFile"] == "AppIcon.icns"
    assert info["CFBundleIdentifier"] == (
        "io.github.ricardomartins-gravitee.openmaskit-companion"
    )
