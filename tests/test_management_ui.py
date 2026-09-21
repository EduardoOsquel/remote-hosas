import os
import sys
import time
from subprocess import CompletedProcess
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from command_log import DIAGNOSTICS
from management_ui import ManagementTab


@pytest.fixture
def management():
    application = QApplication.instance() or QApplication([])
    DIAGNOSTICS.clear()
    with patch.object(ManagementTab, "_is_usbipd_installed", return_value=False), \
            patch.object(ManagementTab, "_is_usbip_win2_installed", return_value=False):
        widget = ManagementTab()
        yield application, widget
        if widget._process is not None:
            widget._process.kill()
            widget._process.waitForFinished()
        widget.deleteLater()
        application.processEvents()


def wait_for_action(application, widget):
    deadline = time.monotonic() + 5
    while widget._process is not None and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    assert widget._process is None


@pytest.mark.parametrize("exit_code", [0, 7])
def test_localized_output_is_preserved_but_ui_stays_english(management, exit_code):
    application, widget = management
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)
    widget._start_command("Test operation", [sys.executable, "-c",
        f"import time; print('Instalado correctamente'); time.sleep(0.1); raise SystemExit({exit_code})"])
    assert not widget.install_usbipd_btn.isEnabled()
    wait_for_action(application, widget)
    timer.stop()
    assert ticks, "The event loop must remain responsive during commands"
    assert "Instalado correctamente" not in widget.log_widget.toPlainText()
    assert "Instalado correctamente" in "\n".join(DIAGNOSTICS)
    assert ("[OK]" if exit_code == 0 else "[ERROR]") in widget.log_widget.toPlainText()
    assert widget.install_usbipd_btn.isEnabled()


def test_missing_executable_recovers_controls(management):
    application, widget = management
    widget._start_command("Test operation", ["nonexistent-usbip-test-executable-987654"])
    wait_for_action(application, widget)
    assert "Could not start" in widget.log_widget.toPlainText()
    assert widget.refresh_btn.isEnabled()


def test_download_and_uninstall_have_distinct_targets(management):
    _, widget = management
    with patch("management_ui.QDesktopServices.openUrl", return_value=True) as open_url:
        widget.install_usbip_win2()
        assert "usbip-win2/releases/latest" in open_url.call_args.args[0].toString()
    with patch.object(widget, "_start_command") as start:
        widget.uninstall_usbip_win2()
        assert start.call_args.args[1] == ["control.exe", "appwiz.cpl"]


def test_diagnostics_export_preserves_original_output(management, tmp_path):
    _, widget = management
    DIAGNOSTICS.append("Original diagnostic: Instalado correctamente")
    destination = tmp_path / "diagnostics.txt"
    with patch("management_ui.QFileDialog.getSaveFileName", return_value=(str(destination), "")):
        widget.export_diagnostics()
    assert "Instalado correctamente" in destination.read_text(encoding="utf-8")
    assert "Diagnostics exported" in widget.log_widget.toPlainText()


def test_usbipd_directory_does_not_mark_client_as_detected(monkeypatch, tmp_path):
    (tmp_path / "Programs" / "usbipd-win").mkdir(parents=True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    with patch("management_ui.shutil.which", return_value=None):
        assert not ManagementTab._component_detected("usbip", "usbip-win2")
        assert ManagementTab._component_detected("usbipd", "usbipd-win")


def test_window_stays_open_during_management_action(management):
    from app import UsbipJoystickBridgeApp
    from PyQt6.QtGui import QCloseEvent

    with patch("app.subprocess.run", return_value=CompletedProcess([], 0, "", "")), \
            patch("app.pygame", None):
        window = UsbipJoystickBridgeApp()
    window.management_tab._process = object()
    event = QCloseEvent()
    window.closeEvent(event)
    assert not event.isAccepted()
    assert window.centralWidget().currentWidget() is window.management_tab
    window.management_tab._process = None
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()
    window.deleteLater()
