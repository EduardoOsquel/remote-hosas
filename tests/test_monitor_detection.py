import os
from unittest.mock import patch, MagicMock
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from app import JoystickTab
from management_ui import ManagementTab

@pytest.mark.parametrize("removed", [False, True])
def test_disconnected_controller_stops_once(removed):
    application = QApplication.instance() or QApplication([])
    with patch("app.pygame", None):
        widget = JoystickTab()
    class DeviceError(Exception):
        pass
    pygame = MagicMock()
    pygame.error = DeviceError
    joystick = MagicMock()
    joystick.get_instance_id.return_value = 42
    joystick.quit.side_effect = DeviceError()
    if removed:
        event = MagicMock()
        event.instance_id = 42
        pygame.event.get.return_value = [event]
    else:
        pygame.event.get.return_value = []
        joystick.get_numaxes.side_effect = DeviceError()
    widget._current_joystick = joystick
    widget._timer = QTimer(widget)
    widget._timer.start(20)
    with patch("app.pygame", pygame):
        widget.read_joystick_state()
        widget.read_joystick_state()
    assert not widget._timer.isActive()
    assert widget._current_joystick is None
    assert widget.monitor_status.text() == "Disconnected"
    assert widget.log.toPlainText().count("Disconnected.") == 1
    widget.deleteLater()


def test_management_uses_host_resolver_and_handles_access_failure():
    application = QApplication.instance() or QApplication([])
    with patch("management_ui.resolve_host", return_value=r"C:\Custom\usbipd.exe"):
        widget = ManagementTab()
        assert widget.usbipd_status.text() == "Detected"
        assert widget.usbipd_status.toolTip() == r"C:\Custom\usbipd.exe"
    with patch("management_ui.resolve_host", side_effect=PermissionError()):
        widget.refresh_installation_status()
        assert widget.usbipd_status.text() == "Unavailable"
        assert not widget.install_usbipd_btn.isEnabled()
        assert not widget.uninstall_usbipd_btn.isEnabled()
    with patch("management_ui.resolve_host", side_effect=FileNotFoundError()):
        widget.refresh_installation_status()
        assert widget.usbipd_status.text() == "Not detected"
    widget.deleteLater()


def test_monitor_toggle_keeps_samples_out_of_log():
    application = QApplication.instance() or QApplication([])
    pygame = MagicMock()
    pygame.error = RuntimeError
    pygame.joystick.get_count.return_value = 1
    pygame.event.get.return_value = []
    device = pygame.joystick.Joystick.return_value
    device.get_name.return_value = "Flight stick"
    device.get_instance_id.return_value = 42
    device.get_guid.return_value = "hardware-guid"
    device.get_numaxes.return_value = 1
    device.get_numbuttons.return_value = 1
    device.get_numhats.return_value = 0
    device.get_axis.return_value = 0.25
    device.get_button.return_value = 1
    with patch("app.pygame", pygame):
        widget = JoystickTab()
        assert "Flight stick" in widget.device_combo.currentText()
        assert "hardware-guid" in widget.device_details.text()
        widget.connect_local_joystick()
        timer = widget._timer
        assert widget.connect_btn.text() == "Stop monitoring"
        before = widget.log.toPlainText()
        widget.read_joystick_state()
        assert "+0.250" in widget.live_state.toPlainText()
        assert widget.log.toPlainText() == before
        widget.connect_local_joystick()
        assert not timer.isActive()
        assert widget._current_joystick is None
        assert widget.connect_btn.text() == "Start monitoring"
        assert widget.device_combo.isEnabled()
        widget.connect_local_joystick()
        assert widget._timer is timer
        widget.stop_monitoring()
        device.get_instance_id.return_value = 99
        widget.connect_local_joystick()
        assert widget.monitor_status.text() == "Disconnected"
        assert widget._current_joystick is None
    widget.deleteLater()
