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
