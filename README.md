# HOSAS + PyQt6 Joystick Bridge

A desktop interface for USB/IP component management and local joystick capture.
The application UI and activity messages are in English.

## Requirements

- Python 3.10+
- PyQt6
- pygame
- pytest for tests

```bash
pip install PyQt6 pygame pytest
python app.py
```

The previous `python usbip_ui.py` entry point opens the same application.

## Project structure

- `app.py`: main window, Host, Client and Joystick tabs.
- `management_ui.py`: component cards, detection and asynchronous management actions.
- `ui_theme.py`: shared colors, controls and spacing.
- `ui_icons.py`: vector icons with normal and disabled states.
- `command_log.py`: English command summaries and original diagnostic output.
- `usbip_manager.py`: USB/IP command builders and device-list parsing.
- `usbip_installer.py`: official release selection, verified downloads and installer execution.
- `joystick_bridge.py`: joystick state and packet serialization.
- `usbip_ui.py`: compatibility launcher.
- `tests/`: command, serialization and UI regression tests.

## Interface

Host keeps the device table at the available width after refresh. DEVICE absorbs
extra space while the other columns fit their content. Drag the separator to
adjust table and log height. Table and dropdown selection remain synchronized,
and refresh preserves the selected BUSID when it is still available.

Management groups usbipd-win and usbip-win2 into separate cards. usbipd-win detection
checks PATH and standard installation directories. usbip-win2 detection uses its
official Inno Setup application ID in both Windows registry views, including custom
installation locations. Uninstall is enabled only when its registered uninstaller
exists, and both actions are disabled while an operation is running.

Install for usbip-win2 queries the official GitHub latest stable release, selects
the x64 or ARM64 installer, checks the downloaded size and published SHA-256 digest,
and requires a valid Authenticode signature before requesting administrator access.
Temporary downloads are removed after the action. Installation and removal use the
vendor's installer, do not automatically restart Windows, and refresh detection
after completion. USB devices may briefly reconnect during driver installation.
No test-signing or Secure Boot settings are changed by this application.

Compatibility policy: the installed usbipd-win version is read and reported, but
upstream publishes no version-pair compatibility matrix. The latest stable client
is selected according to the documented Windows requirements (Windows 10 build
18362+ on x64, Windows 11 on ARM64); the vendor installer enforces its own additional
requirements. The server must support USB/IP 1.1.1. This is not a guarantee for every
usbipd-win release or USB device. A local server is optional because it may run on
another computer. If usbipd-win is not found locally, Install explicitly defaults
to the latest stable usbip-win2 release from the official GitHub repository,
with the same architecture, checksum and signature checks. Unknown architectures, missing assets or checksums, and failed
verification stop the action rather than falling back to an older or unverified file.

Upstream references:

- [Client requirements](https://github.com/vadimgrn/usbip-win2#requirements)
- [Official releases](https://github.com/vadimgrn/usbip-win2/releases/latest)
- [Installer application ID and behavior](https://github.com/vadimgrn/usbip-win2/blob/master/userspace/innosetup/setup.iss)
- [Inno Setup command-line options](https://jrsoftware.org/ishelp/topic_setupcmdline.htm)

Management commands run asynchronously. The interface shows English outcome
messages and exit codes, while Export diagnostics saves the original tool output
as UTF-8. External programs, Windows dialogs and device names can still use the
system language. Clear log clears visible activity, not retained diagnostics.
Diagnostics stay in memory (the latest 100 records) until exported or the app exits.
The window remains open while a management command is running.

## Current scope

The Joystick tab detects local controllers, reads axes, buttons and hats every
20 ms, and builds a Python dictionary packet. Network transmission and remote
virtual-joystick playback are not implemented yet. USB/IP actions invoke external
tools and require the appropriate tools and permissions on the target system.

## Tests

```bash
python -m pytest -q -p no:cacheprovider
```

UI tests use Qt's offscreen platform. Management tests launch harmless Python
processes to verify responsiveness and English summaries; they do not install or
uninstall components. Installer tests mock downloads, registry detection and
installer execution, including integrity failures, missing installations and UAC
cancellation. A real driver installation is not part of the test suite.
