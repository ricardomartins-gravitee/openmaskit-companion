# Automated test coverage

The suites use temporary homes, synthetic MCPs and disposable Docker projects.
They do not open an installed Companion, use mailbox tools or borrow personal
encryption keys. A passing suite is evidence for the tested cases, not a promise
that every platform or failure is covered.

| Layer | Executable checks | Evidence |
| --- | --- | --- |
| Native screens | Render onboarding, Installation, Local MCPs and General; press native accessibility controls; edit the address; toggle startup; test busy/error/disabled states | XCTest and synthetic PNG snapshots on Apple Silicon and Intel |
| Native model | Real bounded helper processes with fixture responses; setup, attachment, registration, dashboard validation, stale refresh races, duplicate submissions, missing Docker and repair | XCTest |
| App lifecycle | Onboarding completion, configured menu-only launch, reopening one Settings window, closing the last window, Quit stopping the owned connector | XCTest with an isolated model and defaults domain |
| Backend | CLI routes, persistent selection, local origins, scoped Docker commands, prerequisite failures, registration, protocol keepalive, credentials and error redaction | pytest, JUnit and statement/branch reports |
| Connector integration | Pairing, locally approved processes, streamable HTTP, reconnect, no replay, independent sessions and process cleanup | Pinned connector suite and disposable Docker manager acceptance |
| Privacy and web | Field rules, aliases, Presidio, analyzer outages, server isolation, persistence, browser workflows and real startup | OpenMaskit fork's unit/browser/real-model suites |
| Shared design | Token validation, generated outputs, contrast, actual native rendering, Chromium and WebKit layouts and control states | Design-system repository suites |
| Distribution | Locked source and release metadata, checksums/provenance rejection, bundle identity/icons and actual packaged CLI contract | pytest and packaging acceptance |

## Gates and reports

Backend coverage is checked per module: at least 95% of statements and 90% of
branches, plus 95% combined overall. A missing module report fails the check.
The separate counters prevent a strong module from hiding a weak one.

Both Mac jobs instrument Swift tests and retain native coverage plus synthetic
screen snapshots. Screenshots are review evidence and layout/render checks;
there is no universal pixel baseline across OS versions, architectures or fonts.
Native coverage includes only code executed inside the test runner; separate
cross-process and Docker checks provide additional behavioral evidence.

## Explicit boundaries

In-process accessibility actions exercise the app's own rendered controls. They
do not certify VoiceOver's complete interaction model, every keyboard setting,
the OS's menu-bar overflow behavior or system-owned file/permission dialogs.
Those remain focused interactive acceptance checks. The app's menu states,
action guards, controller routing and permanent menu policy have automated tests.

Signing/notarization and a product-level updater are not implemented features;
tests must not claim to validate a production installer or updater that does not
exist. Release-verification and backup-preservation tests cover the available
development tooling. Test failures must not be hidden by increasing retries,
silently skipping required fixtures or disabling security checks.
