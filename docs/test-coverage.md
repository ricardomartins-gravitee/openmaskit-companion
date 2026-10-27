# Automated test coverage

The suites use temporary homes, synthetic MCPs and disposable Docker projects.
They do not open an installed Companion, use mailbox tools or borrow personal
encryption keys. A passing suite is evidence for the tested cases, not a promise
that every platform or failure is covered.

| Layer | Executable checks | Evidence |
| --- | --- | --- |
| Native screens/components | Render full Settings with its real bounded scroll container; independently host the same section selector/content components and onboarding; drive their native controls, edit the address, toggle startup and verify busy/error/disabled states | XCTest and synthetic PNG snapshots on Apple Silicon and Intel |
| Native model | Real bounded helper processes with fixture responses; setup, attachment, registration, dashboard validation, stale refresh races, duplicate submissions, missing Docker and repair | XCTest |
| App lifecycle | Onboarding completion, configured menu-only launch, reopening one Settings window, retaining the actual native status item across last-window closure, Quit stopping the owned connector | XCTest with an isolated model and defaults domain, plus packaged native process acceptance with a synthetic backend |
| Backend | CLI routes, persistent selection, local origins, scoped Docker commands, prerequisite failures, registration, protocol keepalive, credentials and error redaction | pytest, JUnit and statement/branch reports |
| Connector integration | Pairing, locally approved processes, streamable HTTP, reconnect, no replay, independent sessions and process cleanup | Pinned connector suite and disposable Docker manager acceptance |
| Privacy and web | Field rules, aliases, Presidio, analyzer outages, server isolation, persistence, browser workflows and real startup | OpenMaskit fork's unit/browser/real-model suites |
| Shared design | Token validation, generated outputs, contrast, actual native rendering, Chromium and WebKit layouts and control states | Design-system repository suites |
| Distribution | Locked source and release metadata, checksums/provenance rejection, bundle identity/icons and actual packaged CLI contract | pytest and packaging acceptance |

## Gates and reports

Backend coverage is checked per module: at least 95% of statements and 90% of
branches, plus 95% combined overall. A missing module report fails the check.
The separate counters prevent a strong module from hiding a weak one.

Native tests start before the slower Intel library verification and Docker
integration. The existing required Mac check names still require successful
native, integration and packaged-app matrices; failure, cancellation and skipped
jobs cannot produce a passing gate. The gate's status combinations are tested.

Both Mac jobs instrument Swift tests and retain native coverage plus synthetic
screen snapshots. Screenshots are review evidence and layout/render checks;
there is no universal pixel baseline across OS versions, architectures or fonts.
Native coverage includes only code executed inside the test runner; separate
cross-process and Docker checks provide additional behavioral evidence.

## Explicit boundaries

In-process actions exercise the app's own rendered components. The headless
runner exposes onboarding and menu controls, but does not populate the nested
SwiftUI Settings scroll-content accessibility tree. Settings control tests host
the same production selector/content components directly; separate tests render
the full scroll window and check its bounded layout. No alternate action logic
or test-only branch is added to the app. Live scrolling, focus across the scroll
boundary and accessibility traversal through that container remain acceptance
checks. These suites do not certify VoiceOver's complete interaction model, every keyboard setting,
the OS's menu-bar overflow behavior or system-owned file/permission dialogs.
Those remain focused interactive acceptance checks. The app's menu states,
action guards, controller routing and permanent menu policy have automated tests.

Signing/notarization and a product-level updater are not implemented features;
tests must not claim to validate a production installer or updater that does not
exist. Release-verification and backup-preservation tests cover the available
development tooling. Test failures must not be hidden by increasing retries,
silently skipping required fixtures or disabling security checks.
