from __future__ import annotations

import re
import os
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import List


@dataclass
class UsbipDevice:
    busid: str
    name: str
    vid_pid: str = ""
    state: str = ""


def parse_usbipd_list(output: str) -> List[UsbipDevice]:
    devices: List[UsbipDevice] = []
    lines = output.splitlines()
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        index += 1

        if not stripped:
            continue
        if stripped.lower().startswith("busid"):
            continue
        if stripped.startswith("-") or stripped.startswith("DEVICE"):
            continue
        if stripped.upper().startswith("GUID"):
            continue

        if not re.match(r"^\d+-\S+", stripped):
            continue

        parts = stripped.split()
        busid = parts[0]
        if len(parts) >= 3 and ":" in parts[1]:
            vid_pid = parts[1]
            remainder = " ".join(parts[2:])
        else:
            vid_pid = ""
            remainder = " ".join(parts[1:])

        state = ""
        if not remainder:
            if index < len(lines):
                next_line = lines[index].strip()
                if next_line in {"Not shared", "Shared", "Shared (forced)", "Attached"}:
                    state = next_line
                    index += 1
            devices.append(UsbipDevice(busid=busid, name="", vid_pid=vid_pid, state=state))
            continue

        if any(remainder.endswith(state) for state in ("Not shared", "Shared", "Shared (forced)", "Attached")):
            device_name, state = _split_device_and_state(remainder)
            devices.append(UsbipDevice(busid=busid, name=device_name, vid_pid=vid_pid, state=state))
            continue

        if index < len(lines):
            next_line = lines[index].strip()
            if next_line in {"Not shared", "Shared", "Shared (forced)", "Attached"}:
                state = next_line
                index += 1

        devices.append(UsbipDevice(busid=busid, name=remainder.strip(), vid_pid=vid_pid, state=state))

    return devices


def _split_device_and_state(value: str) -> tuple[str, str]:
    if not value:
        return "", ""

    for state in ("Not shared", "Shared (forced)", "Shared", "Attached"):
        if value.endswith(state):
            return value[: -(len(state))].rstrip(), state

    return value.strip(), ""


def build_usbipd_bind_command(busid: str) -> List[str]:
    return ["usbipd", "bind", f"--busid={busid}"]


def build_usbipd_unbind_command(busid: str) -> List[str]:
    return ["usbipd", "unbind", f"--busid={busid}"]


USBIP_TCP_PORT = 3240


def build_usbip_list_command(host: str, tcp_port: int = USBIP_TCP_PORT) -> List[str]:
    return ["usbip", f"--tcp-port={tcp_port}", "list", "-r", host]


def build_usbip_attach_command(host: str, busid: str, tcp_port: int = USBIP_TCP_PORT) -> List[str]:
    return ["usbip", f"--tcp-port={tcp_port}", "attach", "-r", host, "-b", busid, "--once"]


def build_usbip_detach_command(port: str) -> List[str]:
    if not str(port).isdigit() or not 1 <= int(port) <= 255:
        raise ValueError("Select an imported device's virtual port (1-255).")
    return ["usbip", "detach", "-p", str(int(port))]


def build_usbip_detach_all_command() -> List[str]:
    return ["usbip", "detach", "--all"]


def resolve_usbip_client() -> str:
    # The official installer need not add its folder to this process's PATH.
    from usbip_installer import find_client_installation
    installation = find_client_installation()
    if installation and installation.uninstaller:
        candidate = installation.uninstaller.parent / "usbip.exe"
        if candidate.is_file():
            return str(candidate)
    for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(variable)
        if base:
            candidate = Path(base) / "USBip" / "usbip.exe"
            if candidate.is_file():
                return str(candidate)
    executable = shutil.which("usbip")
    if executable:
        return executable
    raise FileNotFoundError("usbip.exe")


def parse_remote_devices(output: str) -> List[UsbipDevice]:
    devices = []
    for line in output.splitlines():
        match = re.match(r"^\s*(\d+-[\d.]+)\s*:\s*(.+)$", line)
        if match:
            busid, name = match.groups()
            devices.append(UsbipDevice(busid, name.strip(), state="Exportable"))
    return devices


@dataclass
class ImportedDevice:
    port: int
    name: str
    location: str = ""


def parse_imported_devices(output: str) -> List[ImportedDevice]:
    devices = []
    current = None
    for line in output.splitlines():
        match = re.match(r"^\s*Port\s+(\d+)\s*:", line, re.I)
        if match:
            port = int(match[1])
            current = ImportedDevice(port, "USB device") if 1 <= port <= 255 else None
            if current:
                devices.append(current)
        elif current and "usbip://" in line:
            current.location = line.split("usbip://", 1)[1].strip()
        elif current and line.strip() and not line.strip().startswith("->") and current.name == "USB device":
            current.name = line.strip()
    return devices


def build_usbipd_install_command() -> List[str]:
    return ["winget", "install", "usbipd", "--accept-source-agreements", "--accept-package-agreements"]


def build_usbip_win2_install_command() -> List[str]:
    return [sys.executable, "-u", str(Path(__file__).with_name("usbip_installer.py")), "install"]


def build_usbip_win2_uninstall_command() -> List[str]:
    return [sys.executable, "-u", str(Path(__file__).with_name("usbip_installer.py")), "uninstall"]
