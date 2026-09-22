"""Official usbip-win2 installation workflow, run in a separate process.

Compatibility is based on upstream Windows/architecture requirements, not an
invented usbipd/client version matrix. No system changes occur when importing.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen
from restore_point import create_restore_point, RestorePointError


LATEST_URL = "https://api.github.com/repos/vadimgrn/usbip-win2/releases/latest"
DOWNLOAD_PREFIX = "https://github.com/vadimgrn/usbip-win2/releases/download/"
UNINSTALL_KEY = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                 r"\{199505b0-b93d-4521-a8c7-897818e0205a}_is1")
MAX_DOWNLOAD = 200 * 1024 * 1024


class InstallError(Exception):
    """A message safe to display in the English application log."""


@dataclass(frozen=True)
class ClientInstallation:
    version: str
    uninstaller: Path | None


def find_client_installation():
    if sys.platform != "win32":
        return None
    import winreg

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY, 0, winreg.KEY_READ | view) as key:
                    def value(name):
                        try:
                            return str(winreg.QueryValueEx(key, name)[0])
                        except OSError:
                            return ""
                    version = value("DisplayVersion")
                    command = value("UninstallString")
                    match = re.fullmatch(r'"([^"\r\n]+\.exe)"', command, re.I)
                    if match:
                        path = Path(match[1])
                    elif command.lower().endswith(".exe") and '"' not in command:
                        path = Path(command)
                    else:
                        path = None
                    if path and (not path.is_absolute() or not path.is_file()
                                 or not re.fullmatch(r"unins\d+\.exe", path.name, re.I)):
                        path = None
                    return ClientInstallation(version, path)
            except OSError:
                continue
    return None


def supported_architecture(system=None, machine=None, build=None):
    system = system or sys.platform
    machine = (machine or os.environ.get("PROCESSOR_ARCHITEW6432")
               or os.environ.get("PROCESSOR_ARCHITECTURE") or platform.machine()).lower()
    if system != "win32":
        raise InstallError("Automatic installation requires Windows.")
    build = sys.getwindowsversion().build if build is None else build
    if machine in ("amd64", "x86_64", "x64") and build >= 18362:
        return "x64"
    if machine in ("arm64", "aarch64") and build >= 22000:
        return "arm64"
    raise InstallError("Requires Windows 10 1903 or newer (x64), or Windows 11 (ARM64).")


def host_version():
    executable = shutil.which("usbipd")
    if not executable:
        for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(variable)
            candidate = Path(base) / "usbipd-win" / "usbipd.exe" if base else None
            if candidate and candidate.is_file():
                executable = str(candidate)
                break
    if not executable:
        return None
    result = subprocess.run([executable, "--version"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=15,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    match = re.search(r"\b\d+\.\d+\.\d+(?:\.\d+)?\b", result.stdout)
    if result.returncode or not match:
        raise InstallError("Could not read the installed usbipd-win version.")
    return match[0]


def select_asset(release, architecture):
    if release.get("draft") or release.get("prerelease"):
        raise InstallError("The release is not a stable public release.")
    tag = release.get("tag_name", "")
    match = re.fullmatch(r"[vV]\.?([0-9]+(?:\.[0-9]+){2,3})", tag)
    if not match:
        raise InstallError("The release version format is not supported.")
    version = match[1]
    name = f"USBip-{version}-{architecture}.exe"
    assets = [asset for asset in release.get("assets", []) if asset.get("name") == name]
    if len(assets) != 1:
        raise InstallError("The latest stable release has no matching Windows installer.")
    asset = assets[0]
    if asset.get("browser_download_url") != f"{DOWNLOAD_PREFIX}{tag}/{name}":
        raise InstallError("The installer URL does not belong to the official release.")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", asset.get("digest") or ""):
        raise InstallError("The official release has no SHA-256 digest; installation stopped.")
    if not 0 < asset.get("size", 0) <= MAX_DOWNLOAD:
        raise InstallError("The installer size is invalid.")
    return version, asset


def request(url):
    return urlopen(Request(url, headers={"User-Agent": "Remote-HOSAS",
                                        "Accept": "application/vnd.github+json"}), timeout=30)


def download_asset(asset, destination, notify):
    digest = hashlib.sha256()
    received = 0
    last_percent = -10
    with request(asset["browser_download_url"]) as response, destination.open("wb") as output:
        while chunk := response.read(256 * 1024):
            received += len(chunk)
            if received > asset["size"]:
                raise InstallError("The installer download exceeds its expected size.")
            digest.update(chunk)
            output.write(chunk)
            percent = received * 100 // asset["size"]
            if percent >= last_percent + 10:
                notify(f"Downloading usbip-win2: {percent}%")
                last_percent = percent
    if received != asset["size"] or digest.hexdigest() != asset["digest"][7:].lower():
        raise InstallError("Installer verification failed: the size or SHA-256 digest does not match.")


def powershell(script, environment):
    # Dynamic paths are environment values, never interpolated into shell code.
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        env={**os.environ, **environment}, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.stdout:
        print(result.stdout, file=sys.stderr)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


def run_installer(path, uninstall=False):
    script = """$ErrorActionPreference = 'Stop'
try {
    if ($env:USBIP_SETUP_REMOVE -ne '1') {
        $signature = Get-AuthenticodeSignature -LiteralPath $env:USBIP_SETUP_PATH
        if ($signature.Status -ne 'Valid') { exit 40 }
    }
    $setupArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    if ($env:USBIP_SETUP_REMOVE -ne '1') { $setupArgs += @('/SP-', '/RESTARTEXITCODE=3010') }
    $child = Start-Process -FilePath $env:USBIP_SETUP_PATH -ArgumentList $setupArgs -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    exit $child.ExitCode
} catch {
    Write-Error $_ -ErrorAction Continue
    exit 41
}
"""
    code = powershell(script, {"USBIP_SETUP_PATH": str(path),
                              "USBIP_SETUP_REMOVE": "1" if uninstall else "0"})
    if code == 40:
        raise InstallError("The installer signature is not valid; execution was blocked.")
    if code == 41:
        raise InstallError("The installer could not start or administrator permission was declined.")
    if code not in (0, 3010):
        raise InstallError(f"The installer failed or was cancelled (exit code: {code}).")
    return code


def install(notify, create_restore=True):
    architecture = supported_architecture()
    if find_client_installation():
        raise InstallError("usbip-win2 is already installed. Refresh the component status.")
    version = host_version()
    if version:
        notify(f"Installed usbipd-win: {version}.")
    else:
        notify("usbipd-win was not found. Installing the latest stable usbip-win2 release from the official GitHub repository.")
    notify("No publisher version-pair matrix is available. The server must support USB/IP 1.1.1.")
    notify("Checking the latest stable official release...")
    with request(LATEST_URL) as response:
        release = json.loads(response.read(2 * 1024 * 1024))
    version, asset = select_asset(release, architecture)
    notify(f"Selected usbip-win2 {version} for {architecture}.")
    with tempfile.TemporaryDirectory(prefix="remote-hosas-usbip-") as directory:
        installer = Path(directory) / asset["name"]
        download_asset(asset, installer, notify)
        if create_restore:
            create_restore_point(notify, powershell)
        else:
            notify("Restore-point creation was explicitly skipped. Installing without a new restore point.")
        notify("Download verified. Starting installation; Windows may request administrator access.")
        code = run_installer(installer)
    if not find_client_installation():
        raise InstallError("The installer finished, but usbip-win2 is not registered as installed.")
    notify("usbip-win2 installed. Restart Windows to finish driver setup." if code == 3010 else
           "usbip-win2 installed successfully.")
    return code


def uninstall(notify):
    installation = find_client_installation()
    if not installation or not installation.uninstaller:
        raise InstallError("No registered usbip-win2 uninstaller was found.")
    notify("Uninstalling usbip-win2; Windows may request administrator access.")
    code = run_installer(installation.uninstaller, uninstall=True)
    if find_client_installation():
        raise InstallError("usbip-win2 is still registered. Removal may be incomplete; refresh after restarting Windows.")
    notify("usbip-win2 removed. A Windows restart may be required.")
    return code


def main():
    def notify(message):
        print(json.dumps({"message": message}), flush=True)
    try:
        args = sys.argv[1:]
        action = args[0] if args else ""
        if args not in (["install"], ["install", "--skip-restore-point"], ["uninstall"]):
            raise InstallError("Unknown installation action.")
        if action not in ("install", "uninstall"):
            raise InstallError("Unknown installation action.")
        return install(notify, create_restore="--skip-restore-point" not in args) if action == "install" else uninstall(notify)
    except RestorePointError as error:
        notify(f"[ERROR] {error}")
        return 50
    except InstallError as error:
        notify(f"[ERROR] {error}")
    except Exception as error:
        print(repr(error), file=sys.stderr)
        notify("[ERROR] The action could not finish. Check the connection and export diagnostics for details.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
