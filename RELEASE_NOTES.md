# v0.0.2 - Public testing release

- Clearer Host and Client tables, state-dependent double-click actions and separate connected-device tracking across hosts.
- Collapsible activity logs, consistent status presentation and improved spacing.
- Joystick controller table, explicit Apply alias, aliases retained on refresh, visual indicators and raw values in one panel.
- Optional device-name metadata service with source-IP access controls; HTTP transport remains unchanged.
- Self-connection protection, including asynchronous DNS alias checks with a five-second deadline.
- Tray connection actions re-query the host before attaching; unavailable devices are removed from the refreshed list.
- Local sharing changes invalidate stale Client/tray discovery; successful empty lists and failed queries have different messages.

## Pending hardware validation

- End-to-end tests on two Windows PCs, including network loss, USB removal and exit during an operation.
- Physical T.16000M and TWCS monitoring tests. Automated input simulations are not hardware validation.

## Download

Download RemoteHosas.exe (Windows x64) and SHA256SUMS.txt. No application installer or Python installation is needed. The executable is unsigned; USB/IP components and drivers remain separate prerequisites.

Validation: 206 automated tests passed. Physical hardware and two-PC testing listed above remain pending.

# v0.0.1 — First public testing release

Windows-to-Windows USB/IP sharing with a desktop interface and system tray controls.

- Host device discovery, administrator-assisted sharing and state-aware actions.
- Client remote listing, attach/detach and disconnect all.
- Verified official client downloads and optional Windows restore-point creation (enabled by default).
- Local/imported joystick monitoring with disconnection handling.
- Native dark Windows tray menus and device-type icons.
- Quiet background checks, responsive command coordination and controlled exit cleanup.
- Saved connection/window preferences, diagnostics export and About.

## Download

Download **RemoteHosas.exe** (Windows x64) and launch it. No Python installation or application installer is required. USB/IP server/client components remain separate and can be managed from the application. The executable is unsigned.

**SHA256SUMS.txt** provides the executable checksum. See the README for the host/client setup guide, network requirements and current limitations.

This is an initial testing release. Real hardware and network compatibility depend on the upstream drivers. Host shares remain after application exit; imported client devices are disconnected on explicit exit.
