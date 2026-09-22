# HOSAS + PyQt6 Joystick Bridge

A Windows-to-Windows USB/IP interface and local joystick monitor.
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

- `app.py`: main window, Host and Joystick tabs.
- `client_ui.py`: asynchronous Windows client commands, remote exports and imported devices.
- `management_ui.py`: component cards, detection and asynchronous management actions.
- `ui_theme.py`: shared colors, controls and spacing.
- `ui_icons.py`: vector icons with normal and disabled states.
- `app_icon.py`: window icon and Windows application identity.
- `system_tray.py`: tray icon, restore action and explicit close choices.
- `assets/remote-hosas.svg`: original twin-joystick H/bridge artwork.
- `assets/remote-hosas.png`: 512px preview with transparent outer corners.
- `assets/remote-hosas.ico`: Windows icon with 16, 24, 32, 48, 64, 128 and 256px images.
- `command_log.py`: English command summaries and original diagnostic output.
- `usbip_manager.py`: USB/IP command builders and device-list parsing.
- `usbip_installer.py`: official release selection, verified downloads and installer execution.
- `restore_point.py`: elevated Windows restore-point creation and verification.
- `joystick_bridge.py`: joystick state and packet serialization.
- `usbip_ui.py`: compatibility launcher.
- `tests/`: command, serialization and UI regression tests.

## Interface

### Windows-to-Windows connection

1. On the Windows PC with the physical USB device, install **usbipd-win** in
   Management. In Host Mode, list devices and **Bind / Share** the desired BUSID.
   Bind and Unbind need administrator rights on that PC.
2. On the receiving Windows PC, install **usbip-win2** in Management. In Client
   Mode, enter the host's LAN/Tailscale address. Leave **Server TCP port** at
   **3240** for the normal usbipd-win service.
3. Click **List remote devices**, select an exported device, then **Attach / Connect**.
4. **Refresh connections** reads devices imported into this Windows PC. Select
   an imported device and use **Detach / Disconnect** to release it.
   **Detach all** disconnects every USB/IP device imported into this PC, including
   devices from other hosts. It is enabled only when imported devices are detected. Both detach
   actions refresh connections afterwards; neither stops the remote sharing service.

The server firewall must permit inbound TCP 3240 from the client's network.
The application does not change firewall rules. A custom client TCP port is only
for an explicitly configured network port forward; it does not reconfigure the server.
The virtual port returned by `usbip port` is an assigned USB hub slot (1-255),
not TCP 3240. It is discovered automatically, never populated with example numbers.

Host uses `usbipd list/bind/unbind`. Client uses usbip-win2's `usbip --tcp-port=3240
list -r HOST`, `usbip --tcp-port=3240 attach -r HOST -b BUSID --once`, `usbip port`
and `usbip detach -p VIRTUAL_PORT`. No WSL command is used. Remote queries occur
on request; startup does not contact an example host. Client actions have a 30-second
timeout and refresh imported and remote lists after attach/detach. Changing the
host or TCP port invalidates the previous remote selection.

References: [usbipd-win server setup](https://github.com/dorssel/usbipd-win#how-to-use),
[Windows client commands](https://github.com/vadimgrn/usbip-win2#use-usbipexe-to-attach-remote-devices).

Host keeps the device table at the available width after refresh. DEVICE absorbs
extra space while the other columns fit their content. Drag the separator to
adjust table and log height. Table and dropdown selection remain synchronized,
and refresh preserves the selected BUSID when it is still available.
Bind and Unbind automatically refresh the device list, visible states, count and
selection after each attempt, including failures, without changing table sizing.
Host queries existing devices and share states at startup and reports the shared
device count. Startup also refreshes local client connections.

The application uses its icon in the window and sets a Windows application ID
when started from either launcher. Regenerate the PNG and ICO after editing the
SVG with `python tools/build_icon.py`. The ICO is ready for future packaging;
no executable is built by this project yet. A future packager must include the
`assets` directory alongside the application modules.

Minimizing sends the application to the Windows system tray and keeps background
work running. Click its icon or use **Show application** to restore the window.
The close button offers **Send to System Tray**, **Exit application**, and Cancel.
The tray menu also offers **Exit application**. Exit waits for any active client
or management command to finish rather than terminating it. Closing the application
checks current client connections, disconnects all imported devices, and verifies
that none remain before exiting. If cleanup fails, the window stays open with an
error message. Host shares are preserved. Sending to the tray keeps connections active.
If the system tray is unavailable, minimizing behaves normally and the tray choice
is disabled. Windows controls whether the icon appears directly or in its hidden
icons area; its position can be changed through Windows taskbar settings.

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

Before usbip-win2 installation, **Create a restore point** is checked by default.
Management explains why the driver publisher recommends this step. After download
verification and before running the installer, Windows PowerShell requests
administrator approval and creates a uniquely named `DEVICE_DRIVER_INSTALL` point.
The helper verifies that its description and new sequence number appear in Windows'
restore-point list. A successful process launch alone is not treated as success.

If Windows already has a point from the previous 24 hours, System Protection is
unavailable, elevation is declined, or verification fails, driver installation stops.
The log explains the reason. The user may cancel and fix System Protection, or
explicitly confirm installation without a new point; the confirmation defaults to
No. Unchecking the option also requires this confirmation. No protection settings,
restore-point frequency limits or existing restore points are changed automatically.
The point concerns system changes and is not a personal-file backup. A second UAC
prompt may appear for driver installation. The standalone installer helper defaults
to creating a point too; `install --skip-restore-point` is an explicit opt-out.

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

The Joystick tab monitors controllers visible to local Windows, including those
imported through USB/IP. After attaching a remote joystick, click Refresh controllers
and Start monitoring. It reads axes, buttons and all hats every 20 ms and builds a
Python dictionary packet. The Joystick tab does not implement a separate network
transport: USB/IP forwarding is handled by usbipd-win and usbip-win2. Refreshing
controllers stops an existing monitoring session; select a controller to start again.

## Tests

```bash
python -m pytest -q -p no:cacheprovider
```

UI tests use Qt's offscreen platform. Management tests launch harmless Python
processes to verify responsiveness and English summaries; they do not install or
uninstall components. Installer tests mock downloads, registry detection and
installer execution, including integrity failures, missing installations and UAC
cancellation. A real driver installation is not part of the test suite.
Restore-point creation is also simulated. PowerShell tests parse the scripts
without running their system-changing instructions.

## Command coordination

Host commands run on a worker thread. Listing and Bind/Unbind have a 30-second
execution limit. Bind/Unbind request Windows administrator approval when needed;
UAC cancellation is reported in English. The UAC prompt remains under user control;
the elevated command timeout starts after approval. The application waits for the
operation to finish before permitting exit, and refreshes host state after every
sharing attempt, including failure or cancellation.

A shared operation gate serializes Host, Client and Management commands. Controls
in other tabs are disabled while a command runs, and command entry points also
reject conflicting requests. Host retains the gate through its post-action refresh.
Sending the window to the system tray remains available during operations.

## System tray device menu

The tray offers Open tab shortcuts for Host Mode, Client Mode, Management and
Joystick. Share device lists unshared local devices; Stop sharing lists shared,
forced-shared and attached local devices. Connect device uses the host and TCP
port configured in Client Mode; without a host it opens configuration instead.
Disconnect device lists imported devices with their virtual ports and source
locations. Disconnect all is enabled only when imported devices are detected.

Refresh devices queries Host, local imports and the configured remote host in
sequence without blocking the interface. Menus use the latest queried lists;
use Refresh devices to discover changes made outside this application. No remote
host is contacted merely by opening the tray menu. Actions reuse the tab commands,
including administrator approval, operation locking and post-action refreshes.
Tray actions report command outcomes through Windows notifications and retain
activity in the corresponding tab log. Windows notification settings may suppress
these notifications.

Host Bind and Unbind controls follow the selected device state: only Not shared
can be bound; Shared, Shared (forced) and Attached can be unbound. Management and
Host use the same usbipd executable resolver; an installation folder alone does not
count as detected. Access failures display Unavailable and disable installation
actions until detection succeeds.

Device lists refresh every 30 seconds, including while in the tray, and after the
window regains focus (with a one-second debounce). Refreshes skip busy periods and
never interrupt active commands. They query the configured remote host only when
one has been entered. Joystick removal events and read failures stop monitoring,
show Disconnected and log once. Refresh controllers to start a new session.

Automatic refreshes keep the activity logs quiet when device lists and states are
unchanged. Changes produce one summary per list. A new query failure is reported
once, repeated identical failures are suppressed, and recovery is reported.
Manual actions retain their normal logs; original command diagnostics remain
available for export. These are real read-only queries, not simulated operations.

User preferences are saved automatically with Qt QSettings under RemoteHosas /
USBIPBridge in the current Windows user profile. The remote host, TCP port,
normal window size, maximized state and Host table/log splitter are restored at
startup. Changes are saved after a short debounce and when closing the window.
Invalid stored numbers fall back to defaults. Saving preferences does not attach
or share devices; the normal background read-only refresh still applies.
