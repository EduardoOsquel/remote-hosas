import os
import time
import subprocess
from unittest.mock import patch
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from host_commands import HostWorker, elevation_command
from operation_gate import OperationGate
from app import HostModeTab
from client_ui import ClientModeTab
from management_ui import ManagementTab


def test_worker_keeps_event_loop_responsive():
    app = QApplication.instance() or QApplication([])
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)
    def slow(command):
        time.sleep(.12)
        return subprocess.CompletedProcess(command, 0, "", "")
    with patch("host_commands.execute_host", side_effect=slow):
        worker = HostWorker(["usbipd", "list"])
        worker.start()
        deadline = time.monotonic() + 3
        while worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.002)
        worker.wait()
    timer.stop()
    assert len(ticks) > 3
    assert worker.result.returncode == 0


def test_timeout_propagates_from_worker():
    with patch("host_commands.execute_host", side_effect=subprocess.TimeoutExpired("usbipd", 30)):
        worker = HostWorker(["usbipd", "list"])
        worker.run()
        assert isinstance(worker.error, subprocess.TimeoutExpired)


def test_elevation_rejects_untrusted_arguments():
    import pytest
    with pytest.raises(ValueError):
        elevation_command("usbipd.exe", "bind", "1-1; calc")


def test_shared_gate_blocks_commands_in_other_tabs():
    app = QApplication.instance() or QApplication([])
    gate = OperationGate()
    with patch("app.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")):
        host = HostModeTab(gate)
        client = ClientModeTab(gate)
        management = ManagementTab(gate)
        app.processEvents()
        assert gate.acquire(client)
        assert not host.list_btn.isEnabled()
        assert not management.refresh_btn.isEnabled()
        with patch("management_ui.QProcess") as process:
            management._start_command("Install", ["unused"])
            process.assert_not_called()
        gate.release(client)
        assert host.list_btn.isEnabled()
        assert gate.acquire(management)
        with patch("client_ui.resolve_usbip_client", return_value="unused"), patch("client_ui.QProcess") as process:
            client._run("List", ["usbip", "port"])
            process.assert_not_called()
        gate.release(management)
        for widget in (host, client, management):
            widget.deleteLater()


def test_uac_cancellation_refreshes_and_releases_gate():
    app = QApplication.instance() or QApplication([])
    with patch("app.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")) as command:
        host = HostModeTab()
        app.processEvents()
        command.side_effect = [subprocess.CompletedProcess([], 1223, "", ""),
                               subprocess.CompletedProcess([], 0, "", "")]
        host.run_command("Bind device 1-1", ["usbipd", "bind", "--busid=1-1"], refresh=True)
        assert "approval was cancelled" in host.log_widget.toPlainText()
        assert host.gate.owner is None
        assert not host.is_busy
        assert host.list_btn.isEnabled()
        host.deleteLater()


def test_real_host_worker_holds_gate_through_refresh(monkeypatch):
    import threading
    import app as module
    monkeypatch.setattr(module, "HostWorker", HostWorker)
    app = QApplication.instance() or QApplication([])
    release = threading.Event()
    def command(args):
        release.wait(2)
        return subprocess.CompletedProcess(args, 0, "", "")
    with patch("host_commands.execute_host", side_effect=command):
        host = HostModeTab()
        app.processEvents()
        assert host.is_busy
        assert host.gate.owner is host
        assert not host.list_btn.isEnabled()
        release.set()
        deadline = time.monotonic() + 3
        while host.is_busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.002)
        assert not host.is_busy
        assert host.gate.owner is None
        host.deleteLater()


def test_elevated_scripts_parse_without_execution():
    import base64
    import re
    command = elevation_command(r"C:\Program Files\usbipd-win\usbipd.exe", "bind", "1-1")
    outer = base64.b64decode(command[-1]).decode("utf-16le")
    inner = base64.b64decode(re.search(r"'-EncodedCommand', '([^']+)'", outer).group(1)).decode("utf-16le")
    for script in (outer, inner):
        escaped = script.replace("'", "''")
        parser = "$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseInput('" + escaped + "',[ref]$tokens,[ref]$errors); if ($errors.Count) { $errors | Out-String | Write-Output; exit 1 }"
        result = subprocess.run([command[0], "-NoProfile", "-NonInteractive", "-Command", parser], capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stdout + result.stderr
