# Companion app icon

`AppIcon.png` is a 1024 × 1024 vector rendering with a transparent 80-pixel
outer margin. Its rounded navy tile is made by
[`scripts/render_app_icon.swift`](../../../scripts/render_app_icon.swift) with
AppKit drawing primitives. The tile is `#0B1220`; the two linked
outlines use blue `#58A6FF` and teal `#2DD4BF`. The design is an original
connection symbol for Companion and does not use the OpenMaskit product mark.

To regenerate the PNG and the macOS icon container on macOS:

```sh
swift scripts/render_app_icon.swift desktop/macos/Assets/AppIcon.png
mkdir -p .runtime/AppIcon.iconset
sips -z 16 16 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_16x16.png
sips -z 32 32 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_16x16@2x.png
sips -z 32 32 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_32x32.png
sips -z 64 64 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_32x32@2x.png
sips -z 128 128 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_128x128.png
sips -z 256 256 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_128x128@2x.png
sips -z 256 256 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_256x256.png
sips -z 512 512 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_256x256@2x.png
sips -z 512 512 desktop/macos/Assets/AppIcon.png --out .runtime/AppIcon.iconset/icon_512x512.png
cp desktop/macos/Assets/AppIcon.png .runtime/AppIcon.iconset/icon_512x512@2x.png
iconutil --convert icns --output desktop/macos/Assets/AppIcon.icns .runtime/AppIcon.iconset
```

The checked-in PNG and ICNS are generated assets; the Swift renderer is their
editable vector source. `sips` creates the standard iconset sizes and `iconutil`
creates the macOS ICNS container.
