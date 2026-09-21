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
- `joystick_bridge.py`: joystick state and packet serialization.
- `usbip_ui.py`: compatibility launcher.
- `tests/`: command, serialization and UI regression tests.

## Interface

Host keeps the device table at the available width after refresh. DEVICE absorbs
extra space while the other columns fit their content. Drag the separator to
adjust table and log height. Table and dropdown selection remain synchronized,
and refresh preserves the selected BUSID when it is still available.

Management groups usbipd-win and usbip-win2 into separate cards. Detection checks
PATH and standard installation directories; "Not detected" does not rule out a
custom installation. Refresh status after installing or removing a tool manually.
The usbip-win2 actions open its download page and Windows Programs and Features;
they do not perform installation or removal automatically.

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
uninstall components.
