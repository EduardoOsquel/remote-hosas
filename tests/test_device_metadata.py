import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
from device_metadata import MetadataService, MetadataClient, authorized_addresses, merge_names
from settings_ui import SettingsTab
from usbip_manager import UsbipDevice


def wait_for(app, predicate):
    deadline = time.monotonic() + 4
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_names_require_matching_identity_and_valid_payload():
    devices = [UsbipDevice("2-3", "Original", "05c8:0b10")]
    payload = {"version": 1, "devices": [{"busid": "2-3", "vid_pid": "05c8:0b10", "name": "Camera"}]}
    assert merge_names(devices, payload)[0].name == "Camera"
    assert devices[0].name == "Original"
    payload["devices"][0]["vid_pid"] = "1234:5678"
    assert merge_names(devices, payload) == devices
    assert merge_names(devices, None) == devices
    assert merge_names(devices, {"version": 9}) == devices


def test_access_list_rejects_wildcards_and_networks():
    assert authorized_addresses("127.0.0.1, 192.168.1.2") == {"127.0.0.1", "192.168.1.2"}
    for value in ("*", "192.168.1.0/24", "hostname", "::1"):
        with pytest.raises(ValueError):
            authorized_addresses(value)


def test_service_allows_only_authorized_clients_and_only_shared_devices():
    app = QApplication.instance() or QApplication([])
    service = MetadataService(lambda: [UsbipDevice("1-1", "Camera", "1234:5678", "Shared"),
                                      UsbipDevice("2-1", "Private", "1111:2222", "Not shared")])
    client = MetadataClient()
    results = []
    try:
        service.configure(True, 0, {"127.0.0.1"})
        assert service.server.isListening()
        client.fetch("127.0.0.1", service.server.serverPort(), results.append)
        wait_for(app, lambda: bool(results))
        assert len(results[0]["devices"]) == 1
        assert results[0]["devices"][0]["name"] == "Camera"
        results.clear()
        service.allowed = {"192.0.2.1"}
        client.fetch("127.0.0.1", service.server.serverPort(), results.append)
        wait_for(app, lambda: bool(results))
        assert results == [None]
    finally:
        client.cancel()
        service.stop()


def test_settings_default_off_validation_and_persistence(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "metadata.ini"), QSettings.Format.IniFormat)
    service = MetadataService(lambda: [])
    widget = SettingsTab(settings, service)
    assert not widget.share.isChecked()
    assert not widget.retrieve.isChecked()
    widget.share.setChecked(True)
    widget.apply()
    assert not service.server.isListening()
    assert "authorized" in widget.log_widget.toPlainText()
    widget.share.setChecked(False)
    widget.retrieve.setChecked(True)
    widget.port.setValue(4321)
    widget.apply()
    assert settings.value("metadata/retrieve", type=bool)
    assert settings.value("metadata/port", type=int) == 4321
    widget.deleteLater()
    service.stop()


def test_port_conflict_is_reported_without_stopping_other_server():
    app = QApplication.instance() or QApplication([])
    first = MetadataService(lambda: [])
    second = MetadataService(lambda: [])
    statuses = []
    second.status.connect(statuses.append)
    try:
        first.configure(True, 0, {"127.0.0.1"})
        second.configure(True, first.server.serverPort(), {"127.0.0.1"})
        assert statuses[-1].startswith("Error:")
        assert first.server.isListening()
        assert not second.server.isListening()
    finally:
        first.stop()
        second.stop()


def test_cancelled_lookup_does_not_deliver_names():
    app = QApplication.instance() or QApplication([])
    service = MetadataService(lambda: [])
    client = MetadataClient()
    results = []
    try:
        service.configure(True, 0, {"127.0.0.1"})
        client.fetch("127.0.0.1", service.server.serverPort(), results.append)
        client.cancel()
        for _ in range(10):
            app.processEvents()
        assert results == []
    finally:
        service.stop()


def test_settings_log_explains_only_enabled_retrieval(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "log-settings.ini"), QSettings.Format.IniFormat)
    service = MetadataService(lambda: [])
    widget = SettingsTab(settings, service)
    widget.retrieve.setChecked(True)
    widget.apply()
    assert "List remote devices" in widget.log_widget.toPlainText()
    widget.retrieve.setChecked(False)
    widget.apply()
    assert widget.log_widget.toPlainText().endswith("Remote name retrieval: Disabled.\n")
    assert widget.activity_panel.summary.text() == "[OK] Settings applied."
    assert widget.activity_panel.editor.isHidden()
    service.stop()
    widget.deleteLater()
