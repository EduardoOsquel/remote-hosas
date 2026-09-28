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


@pytest.mark.parametrize("axes_count,buttons_count", [(4, 16), (5, 14), (8, 14)])
def test_hotas_inputs_reach_every_indicator(controllers, axes_count, buttons_count):
    widget, devices, backend = controllers
    device = devices[0]
    device.get_numaxes.return_value = axes_count
    device.get_numbuttons.return_value = buttons_count
    axes = [-1 + 2 * i / (axes_count - 1) for i in range(axes_count)]
    device.get_axis.side_effect = lambda i: axes[i]
    widget.connect_local_joystick()
    widget._timer.stop()
    for pressed in range(buttons_count):
        device.get_button.side_effect = lambda i: i == pressed
        widget.read_joystick_state()
        assert len(widget.axis_bars) == axes_count
        assert len(widget.button_lights) == buttons_count
        assert [b.value() for b in widget.axis_bars] == [round((v + 1) * 1000) for v in axes]
        assert ["ON" in b.text() for b in widget.button_lights] == [i == pressed for i in range(buttons_count)]
    bars = list(widget.axis_bars)
    for x, y, direction in [(0, 0, "Centered"), (0, 1, "Up"), (1, 1, "Up Right"),
                            (1, 0, "Right"), (1, -1, "Down Right"), (0, -1, "Down"),
                            (-1, -1, "Down Left"), (-1, 0, "Left"), (-1, 1, "Up Left")]:
        device.get_hat.return_value = (x, y)
        widget.read_joystick_state()
        assert widget.hat_labels[0].text() == f"Hat 0: {direction}"
        assert widget.axis_bars == bars
    widget.show()
    QApplication.processEvents()
    scroll = widget.live_tabs.widget(0)
    assert scroll.verticalScrollBar().maximum() > 0
    assert all(bar.height() >= 24 for bar in bars)


def test_apply_alias_survives_refresh_with_selected_second_controller(controllers):
    widget, devices, backend = controllers
    widget.controller_table.selectRow(1)
    widget.alias_edit.setText("Right stick")
    widget.apply_alias_btn.click()
    for _ in range(3):
        widget.refresh_devices()
        assert widget.device_combo.currentData()["instance"] == 11
        assert widget.controller_table.currentRow() == 1
        assert widget.alias_edit.text() == "Right stick"
        assert widget.controller_table.item(1, 1).text() == "Right stick"
    assert widget.alias_settings.value("joysticks/aliases/guid1") == "Right stick"


def test_alias_save_updates_existing_cell_only(controllers):
    widget, devices, backend = controllers
    table = widget.controller_table
    items = [[table.item(r, c) for c in range(3)] for r in range(table.rowCount())]
    widget.render_indicators([0.5], [True], [(0, 0)])
    bar = widget.axis_bars[0]
    for alias, save in (("Left", widget.apply_alias_btn.click),
                        ("Flight stick", widget.alias_edit.returnPressed.emit)):
        widget.alias_edit.setText(alias)
        save()
        assert table.item(0, 1).text() == alias
        assert widget.axis_bars[0] is bar
        assert all(table.item(r, c) is item for r, row in enumerate(items)
                   for c, item in enumerate(row))


def test_identical_controller_aliases_survive_refresh_without_overwriting(controllers):
    widget, devices, backend = controllers
    devices[1].get_guid.return_value = "guid0"
    widget.refresh_devices()
    for row, alias in enumerate(("Left", "Right")):
        widget.controller_table.selectRow(row)
        widget.alias_edit.setText(alias)
        widget.apply_alias_btn.click()
    widget.refresh_devices()
    assert widget.controller_table.item(0, 1).text() == "Left"
    assert widget.controller_table.item(1, 1).text() == "Right"
    assert widget.alias_edit.text() == "Right"
