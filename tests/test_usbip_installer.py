import hashlib
from io import BytesIO
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def simulate_restore_point():
    # Tests must never create real system restore points or request elevation.
    with patch("usbip_installer.create_restore_point") as create:
        yield create

from usbip_installer import (ClientInstallation, DOWNLOAD_PREFIX, InstallError, download_asset,
                             LATEST_URL, install, run_installer, select_asset, supported_architecture, uninstall)


def release(architecture="x64"):
    name = f"USBip-0.9.8.0-{architecture}.exe"
    return {"tag_name": "v.0.9.8.0", "draft": False, "prerelease": False, "assets": [{
        "name": name, "browser_download_url": DOWNLOAD_PREFIX + "v.0.9.8.0/" + name,
        "size": 4, "digest": "sha256:" + hashlib.sha256(b"test").hexdigest()}]}


@pytest.mark.parametrize("machine,build,expected", [("AMD64", 18362, "x64"), ("ARM64", 22000, "arm64")])
def test_architecture_selection(machine, build, expected):
    assert supported_architecture("win32", machine, build) == expected


@pytest.mark.parametrize("system,machine,build", [("linux", "AMD64", 26000),
    ("win32", "x86", 26000), ("win32", "AMD64", 17763), ("win32", "ARM64", 19045)])
def test_unsupported_windows_is_rejected(system, machine, build):
    with pytest.raises(InstallError):
        supported_architecture(system, machine, build)


def test_release_selection_excludes_wrong_architecture_prereleases_and_unverified_assets():
    assert select_asset(release(), "x64")[0] == "0.9.8.0"
    invalid = [release("arm64"), {**release(), "prerelease": True}]
    for field, value in (("digest", None), ("browser_download_url", "https://example.com/installer.exe"),
                         ("size", 0)):
        entry = release()
        entry["assets"][0][field] = value
        invalid.append(entry)
    for entry in invalid:
        with pytest.raises(InstallError):
            select_asset(entry, "x64")


def test_download_verifies_hash_and_size(tmp_path):
    asset = release()["assets"][0]
    destination = tmp_path / "setup.exe"
    with patch("usbip_installer.request", return_value=BytesIO(b"test")):
        download_asset(asset, destination, lambda message: None)
    assert destination.read_bytes() == b"test"
    for data in (b"bad!", b"te", b"too long"):
        with patch("usbip_installer.request", return_value=BytesIO(data)), pytest.raises(InstallError):
            download_asset(asset, destination, lambda message: None)


@pytest.mark.parametrize("code", [40, 41, 1, 2])
def test_signature_uac_cancellation_and_installer_errors_are_not_success(code, tmp_path):
    with patch("usbip_installer.powershell", return_value=code), pytest.raises(InstallError):
        run_installer(tmp_path / "setup.exe")


def test_installer_preserves_uac_and_prevents_automatic_reboot(tmp_path):
    path = tmp_path / "space & quote' setup.exe"
    with patch("usbip_installer.powershell", return_value=3010) as run:
        assert run_installer(path) == 3010
    script, environment = run.call_args.args
    assert str(path) not in script
    assert environment["USBIP_SETUP_PATH"] == str(path)
    assert "/NORESTART" in script and "-Verb RunAs" in script
    assert "Get-AuthenticodeSignature" in script


def test_install_checks_registration_after_installer(tmp_path):
    import json
    with patch("usbip_installer.supported_architecture", return_value="x64"), \
            patch("usbip_installer.host_version", return_value="5.3.0"), \
            patch("usbip_installer.find_client_installation", side_effect=[None, ClientInstallation("0.9.8.0", None)]), \
            patch("usbip_installer.request", return_value=BytesIO(json.dumps(release()).encode())), \
            patch("usbip_installer.download_asset"), \
            patch("usbip_installer.run_installer", return_value=3010) as run:
        messages = []
        assert install(messages.append) == 3010
        run.assert_called_once()
        assert any("5.3.0" in message for message in messages)
        assert any("No publisher version-pair matrix" in message for message in messages)


def test_uninstall_cannot_run_without_installation():
    with patch("usbip_installer.find_client_installation", return_value=None), \
            patch("usbip_installer.run_installer") as run, pytest.raises(InstallError):
        uninstall(lambda message: None)
    run.assert_not_called()


def test_failed_verification_never_launches_installer():
    import json
    with patch("usbip_installer.supported_architecture", return_value="x64"), \
            patch("usbip_installer.host_version", return_value="5.3.0"), \
            patch("usbip_installer.find_client_installation", return_value=None), \
            patch("usbip_installer.request", side_effect=[BytesIO(json.dumps(release()).encode()), BytesIO(b"bad!")]), \
            patch("usbip_installer.run_installer") as run, pytest.raises(InstallError, match="verification failed"):
        install(lambda message: None)
    run.assert_not_called()


def test_success_exit_without_registration_is_not_reported_as_installed():
    import json
    with patch("usbip_installer.supported_architecture", return_value="x64"), \
            patch("usbip_installer.host_version", return_value=None), \
            patch("usbip_installer.find_client_installation", return_value=None), \
            patch("usbip_installer.request", return_value=BytesIO(json.dumps(release()).encode())), \
            patch("usbip_installer.download_asset"), \
            patch("usbip_installer.run_installer", return_value=0), \
            pytest.raises(InstallError, match="not registered"):
        install(lambda message: None)


@pytest.mark.parametrize("architecture", ["x64", "arm64"])
def test_missing_host_installs_latest_official_client(architecture):
    import json
    messages = []
    # Exercise the download and integrity check too; only network and execution
    # are simulated. No local usbipd installation is required.
    with patch("usbip_installer.supported_architecture", return_value=architecture), \
            patch("usbip_installer.host_version", return_value=None), \
            patch("usbip_installer.find_client_installation", side_effect=[None, ClientInstallation("0.9.8.0", None)]), \
            patch("usbip_installer.request", side_effect=[BytesIO(json.dumps(release(architecture)).encode()), BytesIO(b"test")]) as request, \
            patch("usbip_installer.run_installer", return_value=0) as run:
        assert install(messages.append) == 0
    assert request.call_args_list[0].args == (LATEST_URL,)
    assert request.call_args_list[1].args == (release(architecture)["assets"][0]["browser_download_url"],)
    assert run.call_args.args[0].name == f"USBip-0.9.8.0-{architecture}.exe"
    assert any("usbipd-win was not found" in message for message in messages)
    assert messages[-1] == "usbip-win2 installed successfully."


def test_powershell_installer_script_parses_without_execution(tmp_path):
    import os
    import shutil
    import subprocess
    if not shutil.which("powershell.exe"):
        pytest.skip("PowerShell is only needed for the Windows installer")
    with patch("usbip_installer.powershell", return_value=0) as run:
        run_installer(tmp_path / "setup.exe")
    script = run.call_args.args[0]
    parser = (
        "$parseTokens = $null; $parseErrors = $null; "
        "[void][System.Management.Automation.Language.Parser]::ParseInput("
        "$env:USBIP_SCRIPT_TO_CHECK, [ref]$parseTokens, [ref]$parseErrors); "
        "if ($parseErrors.Count) { Write-Output $parseErrors; exit 1 }; exit 0"
    )
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", parser],
                            env={**os.environ, "USBIP_SCRIPT_TO_CHECK": script},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_restore_failure_blocks_installer():
    import json
    from restore_point import RestorePointError
    with patch("usbip_installer.supported_architecture", return_value="x64"), \
            patch("usbip_installer.host_version", return_value=None), \
            patch("usbip_installer.find_client_installation", return_value=None), \
            patch("usbip_installer.request", return_value=BytesIO(json.dumps(release()).encode())), \
            patch("usbip_installer.download_asset"), \
            patch("usbip_installer.create_restore_point", side_effect=RestorePointError("Unavailable")), \
            patch("usbip_installer.run_installer") as run, pytest.raises(RestorePointError):
        install(lambda message: None)
    run.assert_not_called()


@pytest.mark.parametrize("enabled", [True, False])
def test_restore_point_precedes_installer_unless_explicitly_skipped(enabled):
    import json
    order = []
    with patch("usbip_installer.supported_architecture", return_value="x64"), \
            patch("usbip_installer.host_version", return_value=None), \
            patch("usbip_installer.find_client_installation", side_effect=[None, ClientInstallation("0.9.8.0", None)]), \
            patch("usbip_installer.request", return_value=BytesIO(json.dumps(release()).encode())), \
            patch("usbip_installer.download_asset"), \
            patch("usbip_installer.create_restore_point", side_effect=lambda *args: order.append("restore")), \
            patch("usbip_installer.run_installer", side_effect=lambda *args: order.append("install") or 0):
        install(lambda message: None, create_restore=enabled)
    assert order == (["restore", "install"] if enabled else ["install"])
