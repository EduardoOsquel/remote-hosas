import os
import sys
import time
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from client_ui import ClientModeTab


REMOTE = "  1-3 : Remote joystick (1234:5678)\n           : /usb/1-3\n"
IMPORTED = "Port 07: device in use at full-speed\n  Remote joystick\n  -> usbip://host-pc:3240/1-3\n"


@pytest.fixture
def client():
    application = QApplication.instance() or QApplication([])
    widget = ClientModeTab()
    yield application, widget
    if widget.is_busy:
        widget._after = None
        widget._process.kill()
        widget._process.waitForFinished()
    widget.deleteLater()
    application.processEvents()


def simulate(widget, output):
    def run(label, command, callback=None, after=None):
        if callback:
            callback(output)
        widget._update_controls()
    return patch.object(widget, "_run", side_effect=run)


def test_client_starts_without_fake_devices_or_ports(client):
    _, widget = client
    assert widget.tcp_port_input.value() == 3240
    assert not widget.attach_btn.isEnabled()
    assert not widget.detach_btn.isEnabled()
    assert widget.port_input.currentData() is None


def test_detach_all_covers_all_hosts_and_refreshes_connections(client):
    _, widget = client
    assert not widget.detach_all_btn.isEnabled()
    from usbip_manager import parse_imported_devices
    widget._set_imported(parse_imported_devices(IMPORTED))
    assert widget.detach_all_btn.isEnabled()
    with patch.object(widget, "_run") as run:
        widget.detach_all_btn.click()
        assert run.call_args.args[1] == ["usbip", "detach", "--all"]
        assert run.call_args.kwargs["after"] == widget._refresh_after_action
    widget._process = object()
    widget._update_controls()
    assert not widget.detach_all_btn.isEnabled()
    with patch.object(widget, "_run") as run:
        widget.detach_all_devices()
        run.assert_not_called()
    widget._process = None
    widget._set_imported([])
    assert not widget.detach_all_btn.isEnabled()


@pytest.mark.parametrize("remaining", ["", IMPORTED])
def test_exit_detaches_and_verifies_fresh_connections(client, remaining):
    _, widget = client
    commands, results = [], []
    outputs = iter([IMPORTED, "", remaining])
    def run(label, command, callback=None, after=None, on_failure=None):
        commands.append(command)
        callback(next(outputs))
    with patch("client_ui.resolve_usbip_client", return_value="usbip.exe"), \
            patch.object(widget, "_run", side_effect=run):
        widget.disconnect_before_exit(results.append)
    assert commands == [["usbip", "port"], ["usbip", "detach", "--all"], ["usbip", "port"]]
    assert results == [not bool(remaining)]


def test_exit_failure_is_reported_and_host_only_can_exit(client):
    _, widget = client
    results = []
    with patch("client_ui.resolve_usbip_client", return_value="usbip.exe"), \
            patch.object(widget, "_run", side_effect=lambda *args, **kwargs: kwargs["on_failure"]()):
        widget.disconnect_before_exit(results.append)
    assert results == [False]
    with patch("client_ui.resolve_usbip_client", side_effect=FileNotFoundError), \
            patch("usbip_installer.find_client_installation", return_value=None):
        widget.disconnect_before_exit(results.append)
    assert results == [False, True]


def test_listing_and_attach_use_remote_host_not_local_usbipd(client):
    _, widget = client
    widget.host_input.setText("host-pc")
    with simulate(widget, REMOTE) as run:
        widget.list_btn.click()
        assert run.call_args.args[1] == ["usbip", "--tcp-port=3240", "list", "-r", "host-pc"]
    assert widget.attach_btn.isEnabled()
    with patch.object(widget, "_run") as run:
        widget.attach_btn.click()
        assert run.call_args.args[1] == ["usbip", "--tcp-port=3240", "attach", "-r", "host-pc", "-b", "1-3", "--once"]
        assert run.call_args.kwargs["after"] == widget._refresh_after_action


@pytest.mark.parametrize("change", ["host", "tcp"])
def test_endpoint_changes_invalidate_device_selection(client, change):
    _, widget = client
    widget.host_input.setText("host-pc")
    with simulate(widget, REMOTE):
        widget.refresh_remote_devices()
    if change == "host":
        widget.host_input.setText("different-host")
    else:
        widget.tcp_port_input.setValue(4000)
    assert not widget.attach_btn.isEnabled()
    assert widget.devices == []
    with patch.object(widget, "_run") as run:
        widget.attach_selected_device()
        run.assert_not_called()


def test_detach_uses_discovered_virtual_port(client):
    _, widget = client
    with simulate(widget, IMPORTED) as run:
        widget.refresh_imported_devices()
        assert run.call_args.args[1] == ["usbip", "port"]
    assert widget.port_input.currentData() == 7
    with patch.object(widget, "_run") as run:
        widget.detach_btn.click()
        assert run.call_args.args[1] == ["usbip", "detach", "-p", "7"]


def test_missing_client_clears_stale_remote_devices(client):
    _, widget = client
    widget.host_input.setText("host-pc")
    with simulate(widget, REMOTE):
        widget.refresh_remote_devices()
    with patch("client_ui.resolve_usbip_client", side_effect=FileNotFoundError):
        widget.refresh_remote_devices()
    assert widget.devices == []
    assert not widget.attach_btn.isEnabled()
    assert "Install usbip-win2" in widget.log_widget.toPlainText()


def test_client_process_is_responsive_and_parses_results(client):
    application, widget = client
    ticks, output = [], []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(True))
    timer.start(10)
    with patch("client_ui.resolve_usbip_client", return_value=sys.executable):
        widget._run("Test client", ["usbip", "-c", "import time; time.sleep(0.1); print('ready')"], output.append)
    deadline = time.monotonic() + 5
    while widget.is_busy and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    timer.stop()
    assert not widget.is_busy
    assert ticks
    assert output == ["ready\r\n"] or output == ["ready\n"]


def test_timeout_restores_controls_and_does_not_accept_partial_results(client):
    application, widget = client
    outputs = []
    with patch("client_ui.resolve_usbip_client", return_value=sys.executable):
        widget._run("Test timeout", ["usbip", "-c", "import time; time.sleep(10)"], outputs.append)
    widget._timer.start(50)
    deadline = time.monotonic() + 5
    while widget.is_busy and time.monotonic() < deadline:
        application.processEvents()
        time.sleep(0.005)
    assert not widget.is_busy
    assert outputs == []
    assert widget.refresh_imported_btn.isEnabled()
    assert "timed out" in widget.log_widget.toPlainText()


def test_refresh_after_action_checks_local_ports_then_remote_exports(client):
    _, widget = client
    widget.host_input.setText("host-pc")
    commands = []
    def run(label, command, callback=None, after=None):
        commands.append(command)
        if callback:
            callback(IMPORTED if command == ["usbip", "port"] else REMOTE)
        if after:
            after()
    with patch.object(widget, "_run", side_effect=run):
        widget._refresh_after_action()
    assert commands == [["usbip", "port"], ["usbip", "--tcp-port=3240", "list", "-r", "host-pc"]]
    assert widget.port_input.currentData() == 7
    assert widget.device_combo.currentData() == "1-3"


def test_use_this_pc_corrects_endpoint_and_lists_devices(client):
    _, widget = client
    widget.host_input.setText("locahost")
    widget.tcp_port_input.setValue(4321)
    with simulate(widget, REMOTE) as run:
        widget.local_host_btn.click()
    assert widget.host_input.text() == "127.0.0.1"
    assert widget.tcp_port_input.value() == 3240
    assert run.call_args.args[1] == ["usbip", "--tcp-port=3240", "list", "-r", "127.0.0.1"]
    assert widget.devices[0].busid == "1-3"
    assert widget.attach_btn.isEnabled()


def test_local_host_shortcut_respects_management_lock(client):
    _, widget = client
    owner = object()
    widget.gate.acquire(owner)
    assert not widget.local_host_btn.isEnabled()
    with patch.object(widget, "_run") as run:
        widget.use_local_host()
        run.assert_not_called()
    assert widget.host_input.text() == ""
    widget.gate.release(owner)



def test_shutdown_command_reports_lock_conflict(client):
    _, widget = client
    owner = object()
    widget.gate.acquire(owner)
    failed = []
    with patch("client_ui.resolve_usbip_client", return_value="usbip.exe"):
        widget._run("Check connections before exit", ["usbip", "port"], on_failure=lambda: failed.append(True))
    assert failed == [True]
    widget.gate.release(owner)


def test_shutdown_reports_busy_client_instead_of_waiting_forever(client):
    _, widget = client
    widget._process = object()
    result = []
    widget.disconnect_before_exit(result.append)
    assert result == [False]
    widget._process = None



def test_background_remote_query_yields_without_clearing_devices(client):
    from usbip_manager import UsbipDevice
    _, widget = client
    application = QApplication.instance()
    widget.devices = [UsbipDevice("1-3", "Known device")]
    widget.gate.background = True
    with patch("client_ui.resolve_usbip_client", return_value=sys.executable):
        widget._run("List remote devices", ["usbip", "-c", "import time; time.sleep(20)"])
    assert widget._timer.interval() == 5000
    start = time.monotonic()
    widget.gate.prioritize_manual_action()
    while widget.is_busy and time.monotonic() - start < 3:
        application.processEvents()
        time.sleep(.005)
    assert not widget.is_busy
    assert time.monotonic() - start < 3
    assert widget.devices[0].busid == "1-3"
    assert "[ERROR]" not in widget.log_widget.toPlainText()
    assert widget.gate.owner is None
    widget.gate.background = False


def test_manual_action_cannot_be_cancelled_as_background(client):
    from unittest.mock import MagicMock
    _, widget = client
    process = MagicMock()
    widget._process = process
    widget._label = "Attach device"
    widget.gate.background = True
    widget.cancel_background_query()
    process.kill.assert_not_called()
    widget._process = None
    widget.gate.background = False


def test_remote_name_is_clean_and_identifiers_appear_in_details(client):
    _, widget = client
    widget.host_input.setText("host-pc")
    output = "2-3 : Cheng Uei Precision Industry Co., Ltd (Foxlink) : unknown product (05c8:0b10)"
    with simulate(widget, output):
        widget.refresh_remote_devices()
    assert widget.device_combo.currentText() == "2-3 - Cheng Uei Precision Industry Co., Ltd (Foxlink)"
    assert not widget.device_combo.itemIcon(0).isNull()
    assert widget.device_combo.currentData() == "2-3"
    assert "VID:PID: 05c8:0b10" in widget.remote_details.text()
    assert "unknown product" not in widget.remote_details.text()
