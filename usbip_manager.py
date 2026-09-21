from __future__ import annotations

import re
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
                if next_line in {"Not shared", "Shared"}:
                    state = next_line
                    index += 1
            devices.append(UsbipDevice(busid=busid, name="", vid_pid=vid_pid, state=state))
            continue

        if remainder.endswith("Not shared") or remainder.endswith("Shared"):
            device_name, state = _split_device_and_state(remainder)
            devices.append(UsbipDevice(busid=busid, name=device_name, vid_pid=vid_pid, state=state))
            continue

        if index < len(lines):
            next_line = lines[index].strip()
            if next_line in {"Not shared", "Shared"}:
                state = next_line
                index += 1

        devices.append(UsbipDevice(busid=busid, name=remainder.strip(), vid_pid=vid_pid, state=state))

    return devices


def _split_device_and_state(value: str) -> tuple[str, str]:
    if not value:
        return "", ""

    for state in ("Not shared", "Shared"):
        if value.endswith(state):
            return value[: -(len(state))].rstrip(), state

    return value.strip(), ""


def build_usbipd_bind_command(busid: str) -> List[str]:
    return ["usbipd", "bind", f"--busid={busid}"]


def build_usbipd_unbind_command(busid: str) -> List[str]:
    return ["usbipd", "unbind", f"--busid={busid}"]


def build_usbip_attach_command(host: str, busid: str) -> List[str]:
    return ["usbipd", "attach", "--wsl", f"--host={host}", f"--busid={busid}"]


def build_usbip_detach_command(port: str) -> List[str]:
    return ["usbipd", "detach", f"--port={port}"]


def build_usbipd_install_command() -> List[str]:
    return ["winget", "install", "usbipd", "--accept-source-agreements", "--accept-package-agreements"]


def build_usbip_win2_install_command() -> List[str]:
    return [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "Start-Process https://github.com/vadimgrn/usbip-win2/releases/latest -Verb Open",
    ]
