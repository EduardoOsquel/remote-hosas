"""Host command worker; only fixed USB/IP actions can request elevation."""
import base64
import ctypes
import os
import re
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtCore import QThread


def resolve_host():
    found = shutil.which("usbipd")
    if found:
        return found
    for variable in ("ProgramW6432", "ProgramFiles"):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / "usbipd-win" / "usbipd.exe"
            if candidate.is_file():
                return str(candidate)
    raise FileNotFoundError("usbipd")


def encoded(script):
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def elevation_command(executable, action, busid):
    if action not in {"bind", "unbind"} or not re.fullmatch(r"[0-9]+-[0-9]+", busid):
        raise ValueError("Invalid host action")
    quoted = executable.replace("'", "''")
    # The elevated process owns the timeout and stops its own usbipd child.
    inner = f"""
$ErrorActionPreference = 'Stop'
try {{
    $p = Start-Process -FilePath '{quoted}' -ArgumentList @('{action}', '--busid={busid}') -WindowStyle Hidden -PassThru
    if (-not $p.WaitForExit(30000)) {{ $p.Kill(); $p.WaitForExit(); exit 1460 }}
    exit $p.ExitCode
}} catch {{ exit 1 }}
"""
    outer = rf"""
$ErrorActionPreference = 'Stop'
try {{
    $p = Start-Process -FilePath "$PSHOME\powershell.exe" -ArgumentList @('-NoProfile', '-NonInteractive', '-EncodedCommand', '{encoded(inner)}') -Verb RunAs -WindowStyle Hidden -PassThru -Wait
    exit $p.ExitCode
}} catch {{
    $e = $_.Exception
    while ($null -ne $e) {{
        if ($e.NativeErrorCode -eq 1223) {{ exit 1223 }}
        $e = $e.InnerException
    }}
    exit 1
}}
"""
    powershell = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    return [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(outer)]


def execute_host(command):
    executable = resolve_host()
    elevated = command[1] in {"bind", "unbind"} and not ctypes.windll.shell32.IsUserAnAdmin()
    actual = [executable, *command[1:]]
    if elevated:
        actual = elevation_command(executable, command[1], command[2].split("=", 1)[1])
    # UAC is user-controlled: keep the operation reserved until answered.
    # After approval the elevated helper enforces its own 30-second timeout.
    return subprocess.run(actual, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", shell=False, check=False,
                          timeout=None if elevated else 30,
                          creationflags=subprocess.CREATE_NO_WINDOW)


class HostWorker(QThread):
    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self.result = None
        self.error = None
    def run(self):
        try:
            self.result = execute_host(self.command)
        except Exception as error:
            self.error = error
