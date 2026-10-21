# Shared design system

The native SwiftUI app consumes the revision-pinned
[OpenMaskit Design System](https://github.com/ricardomartins-gravitee/openmaskit-design-system)
package. `desktop/macos/Package.swift` selects an exact Git revision and
`Package.resolved` records its resolution. That same revision supplies the web
fork's checked-in CSS assets.

The package owns colours, spacing, typography roles, radii and native panel,
badge and button styles. Companion's `Appearance.swift` supplies aliases and its
existing brand icon. Overview and Settings use shared spacing and typography.
Native system fonts, controls, focus and accessibility semantics are retained.

Companion owns its existing app name, icon, menu bar, Dock, preferences, window
behaviour, lifecycle, services and connector integration. None of these move to
the design package. The package has no web renderer or lifecycle hooks.

Update the exact revision deliberately after the shared tests pass, resolve the
package, run both Mac architecture suites and backend/lifecycle acceptance, and
coordinate the web lock to the same release. No local schedule or automatic
installation is added. Only dark mode is currently supported; a future light
theme requires coordinated web/native acceptance.
