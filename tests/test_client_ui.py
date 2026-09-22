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
