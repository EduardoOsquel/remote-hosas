import os
import sys
import time
from subprocess import CompletedProcess
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QMessageBox

from command_log import DIAGNOSTICS
from management_ui import ManagementTab
from usbip_installer import ClientInstallation


def test_restore_option_defaults_on_and_skip_requires_confirmation(management):
    _, widget = management
    assert widget.restore_check.isChecked()
    widget.restore_check.setChecked(False)
    with patch("management_ui.QMessageBox.warning", return_value=QMessageBox.StandardButton.No), \
            patch.object(widget, "_start_command") as start:
        widget.install_usbip_win2()
        start.assert_not_called()
    with patch("management_ui.QMessageBox.warning", return_value=QMessageBox.StandardButton.Yes), \
            patch.object(widget, "_start_command") as start:
        widget.install_usbip_win2()
        assert start.call_args.args[1][-1] == "--skip-restore-point"


@pytest.mark.parametrize("continue_without", [False, True])
def test_restore_failure_only_restarts_install_after_confirmation(management, continue_without):
    application, widget = management
    with patch.object(widget, "_confirm_without_restore_point", return_value=continue_without) as confirm, \
            patch.object(widget, "_launch_client_install") as launch:
        widget._start_command("Test restore failure", [sys.executable, "-c", "raise SystemExit(50)", "install"], client_action=True)
        wait_for_action(application, widget)
        confirm.assert_called_once_with(failed=True)
        if continue_without:
            launch.assert_called_once_with(create_restore=False)
        else:
            launch.assert_not_called()


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
    with patch.object(widget, "_start_command") as start:
        widget.install_usbip_win2()
        assert start.call_args.args[1][-1] == "install"
        assert start.call_args.kwargs["client_action"]
    installed = ClientInstallation("0.9.8.0", Path("C:/Program Files/USBip/unins000.exe"))
    with patch("management_ui.find_client_installation", return_value=installed), \
            patch.object(widget, "_start_command") as start:
        widget.uninstall_usbip_win2()
        assert start.call_args.args[1][-1] == "uninstall"


def test_client_uninstall_requires_registered_uninstaller(management):
    _, widget = management
    assert not widget.uninstall_usbip_win2_btn.isEnabled()
    with patch("management_ui.find_client_installation", return_value=None), \
            patch.object(widget, "_start_command") as start:
        widget.uninstall_usbip_win2()
        start.assert_not_called()
    installed = ClientInstallation("0.9.8.0", Path("C:/Program Files/USBip/unins000.exe"))
    with patch.object(widget, "_is_usbip_win2_installed", return_value=True), \
            patch("management_ui.find_client_installation", return_value=installed):
        widget.refresh_installation_status()
        assert widget.uninstall_usbip_win2_btn.isEnabled()
        assert not widget.install_usbip_win2_btn.isEnabled()


def test_client_reboot_exit_code_is_success(management):
    application, widget = management
    widget._start_command("Test restart", [sys.executable, "-c", "raise SystemExit(3010)"], client_action=True)
    wait_for_action(application, widget)
    assert "Completed - restart Windows" in widget.operation_status.text()
    assert "[ERROR]" not in widget.log_widget.toPlainText()


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
    with patch.object(window.tray, "choose_close_action", return_value="exit"):
        window.closeEvent(event)
    assert not event.isAccepted()
    assert window.centralWidget().currentWidget() is window.management_tab
    window.management_tab._process = None
    event = QCloseEvent()
    with patch.object(window.tray, "choose_close_action", return_value="exit"), \
            patch.object(window.client_tab, "disconnect_before_exit", side_effect=lambda done: done(True)), \
            patch.object(QApplication.instance(), "quit"):
        window.closeEvent(event)
    assert window._shutdown_ready
    window.deleteLater()
