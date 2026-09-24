from unittest.mock import MagicMock, patch
import pytest
from PyQt6.QtWidgets import QApplication
from app import JoystickTab


@pytest.fixture
def controllers():
    application = QApplication.instance() or QApplication([])
    backend = MagicMock()
    backend.error = RuntimeError
    backend.joystick.get_count.return_value = 2
    backend.event.get.return_value = []
    devices = []
    for i in range(2):
        d = MagicMock()
        d.get_name.return_value = f"Stick {i}"
        d.get_guid.return_value = f"guid{i}"
        d.get_instance_id.return_value = i + 10
        d.get_numaxes.return_value = 1
        d.get_numbuttons.return_value = 1
        d.get_numhats.return_value = 1
        d.get_axis.return_value = 0.0
        d.get_button.return_value = 0
        d.get_hat.return_value = (0, 0)
        devices.append(d)
    backend.joystick.Joystick.side_effect = lambda i: devices[i]
    with patch("app.pygame", backend):
        widget = JoystickTab()
        yield widget, devices, backend
        widget.cancel_identification()
        widget.stop_monitoring(announce=False)
        widget.deleteLater()


def test_alias_persists_and_duplicate_guids_are_session_only(controllers):
    widget, devices, backend = controllers
    widget.alias_edit.setText("Left stick")
    widget.save_alias()
    widget.refresh_devices()
    assert widget.alias_edit.text() == "Left stick"
    devices[1].get_guid.return_value = "guid0"
    widget.refresh_devices()
    assert widget.alias_edit.text() == ""
    widget.alias_edit.setText("Session left")
    widget.save_alias()
    assert widget.alias_settings.value("joysticks/aliases/guid0") == "Left stick"
    widget.device_combo.setCurrentIndex(1)
    assert widget.alias_edit.text() == ""
    widget.device_combo.setCurrentIndex(0)
    assert widget.alias_edit.text() == "Session left"


def test_identification_ignores_jitter_then_selects_pressed_controller(controllers):
    widget, devices, backend = controllers
    widget.identify_controller()
    devices[0].get_axis.return_value = 0.01
    widget.identify_tick()
    assert widget.identify_timer.isActive()
    devices[1].get_button.return_value = 1
    widget.identify_tick()
    assert not widget.identify_timer.isActive()
    assert widget.device_combo.currentIndex() == 1
    assert widget.connect_btn.isEnabled()
    assert widget.monitor_status.text().startswith("Identified:")


@pytest.mark.parametrize("reason", ["timeout", "multiple", "removed"])
def test_identification_releases_devices_on_failure(controllers, reason):
    widget, devices, backend = controllers
    widget.identify_controller()
    if reason == "timeout":
        widget.identify_ticks = 299
    elif reason == "multiple":
        for d in devices:
            d.get_button.return_value = 1
    else:
        backend.event.get.return_value = [MagicMock(instance_id=10)]
    widget.identify_tick()
    assert not widget.identify_timer.isActive()
    assert not widget.identifying
    assert widget.device_combo.isEnabled()
    assert not widget.monitor_status.text().startswith("Identified:")


def test_visual_indicators_update_without_rebuilding(controllers):
    widget, devices, backend = controllers
    widget.render_indicators([-1.0], [False], [(0, 0)])
    bar = widget.axis_bars[0]
    assert bar.value() == 0
    widget.render_indicators([1.0], [True], [(-1, 1)])
    assert widget.axis_bars[0] is bar
    assert bar.value() == 2000
    assert "ON" in widget.button_lights[0].text()
    assert "Up Left" in widget.hat_labels[0].text()
