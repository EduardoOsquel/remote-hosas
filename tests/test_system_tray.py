import os
from subprocess import CompletedProcess
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication

from app import UsbipJoystickBridgeApp
from system_tray import SystemTray


@pytest.fixture
def window():
    application = QApplication.instance() or QApplication([])
    with patch("app.subprocess.run", return_value=CompletedProcess([], 0, "", "")), \
            patch("app.pygame", None), \
            patch.object(SystemTray, "available", return_value=True), \
            patch("system_tray.QSystemTrayIcon.show"), \
            patch("system_tray.QSystemTrayIcon.hide"), \
            patch.object(application, "quit") as quit_app:
        widget = UsbipJoystickBridgeApp()
        widget.show()
        application.processEvents()
        with patch.object(widget.client_tab, "disconnect_before_exit", side_effect=lambda done: done(True)):
            yield application, widget, quit_app
        widget.hide()
        widget.deleteLater()
        application.processEvents()


def test_minimize_hides_and_restore_keeps_maximized_state(window):
    application, widget, quit_app = window
    widget.showMaximized()
    application.processEvents()
    widget.showMinimized()
    application.processEvents()
    assert not widget.isVisible()
    quit_app.assert_not_called()
    widget.tray.show_action.trigger()
    application.processEvents()
    assert widget.isVisible()
    assert widget.isMaximized()


@pytest.mark.parametrize("choice", ["tray", "cancel", "exit"])
def test_close_choices(window, choice):
    _, widget, quit_app = window
    event = QCloseEvent()
    with patch.object(widget.tray, "choose_close_action", return_value=choice):
        widget.closeEvent(event)
    assert not event.isAccepted()  # Exit completes through a second close after cleanup.
    if choice == "exit":
        quit_app.assert_called_once()
    else:
        quit_app.assert_not_called()
        assert widget.isVisible() == (choice == "cancel")


def test_busy_installation_can_be_hidden_but_cannot_be_terminated(window):
    _, widget, quit_app = window
    widget.management_tab._process = object()
    with patch.object(widget.tray, "choose_close_action", return_value="tray"):
        widget.closeEvent(QCloseEvent())
    assert not widget.isVisible()
    widget.tray.exit_action.trigger()
    assert widget.isVisible()
    assert not widget._exit_requested
    quit_app.assert_not_called()
    widget.management_tab._process = None


def test_unavailable_tray_does_not_hide_window(window):
    _, widget, _ = window
    with patch.object(widget.tray, "available", return_value=False):
        assert not widget.tray.hide_window()
    assert widget.isVisible()


def test_tray_exit_exits_without_showing_close_choice_again(window):
    _, widget, quit_app = window
    widget.tray.hide_window()
    with patch.object(widget.tray, "choose_close_action") as choose:
        widget.tray.exit_action.trigger()
        choose.assert_not_called()
    quit_app.assert_called_once()


def test_exit_waits_for_disconnect_and_keeps_window_on_failure(window):
    _, widget, quit_app = window
    callbacks = []
    with patch.object(widget.client_tab, "disconnect_before_exit", side_effect=callbacks.append):
        widget.request_exit()
    quit_app.assert_not_called()
    assert widget._shutdown_pending
    callbacks[0](False)
    assert not widget._shutdown_pending
    assert widget.isVisible()
    quit_app.assert_not_called()


@pytest.mark.parametrize("index,attribute", [(0, "host_tab"), (1, "client_tab"),
                                              (2, "management_tab"), (3, "joystick_tab")])
def test_tray_opens_requested_tab(window, index, attribute):
    _, widget, _ = window
    widget.hide()
    widget.tray.tabs_menu.actions()[index].trigger()
    assert widget.isVisible()
    assert widget.centralWidget().currentWidget() is getattr(widget, attribute)


def test_share_menus_filter_states_and_route_selected_busid(window):
    from usbip_manager import UsbipDevice
    _, widget, _ = window
    host, tray = widget.host_tab, widget.tray
    host._set_devices([UsbipDevice("1-1", "Controller", state="Not shared"),
                       UsbipDevice("1-2", "Camera", state="Shared"),
                       UsbipDevice("1-3", "Adapter", state="Attached")])
    tray.rebuild_devices()
    assert tray.share_menu.actions()[0].text() == "1-1 - Controller"
    assert tray.share_menu.icon().isNull()
    assert len(tray.share_menu.actions()) == 1
    assert len(tray.unshare_menu.actions()) == 2
    with patch.object(host, "bind_selected_device") as bind:
        tray.share_menu.actions()[0].trigger()
        bind.assert_called_once()
        assert host.device_combo.currentData() == "1-1"
    with patch.object(host, "unbind_selected_device") as unbind:
        tray.unshare_menu.actions()[1].trigger()
        unbind.assert_called_once()
        assert host.device_combo.currentData() == "1-3"


def test_client_tray_actions_use_endpoint_and_virtual_port(window):
    from usbip_manager import UsbipDevice, ImportedDevice
    _, widget, _ = window
    client, tray = widget.client_tab, widget.tray
    client.host_input.setText("host-a")
    client.devices = [UsbipDevice("2-1", "Stick")]
    client._listed_endpoint = client._endpoint()
    client.device_combo.clear()
    client.device_combo.addItem("Stick", "2-1")
    client._set_imported([ImportedDevice(7, "Stick", "host-a:3240/2-1")])
    tray.rebuild_devices()
    with patch.object(client, "attach_selected_device") as attach:
        tray.connect_menu.actions()[1].trigger()
        attach.assert_called_once()
        tray.connect_device("2-1", ("other-host", 3240))
        attach.assert_called_once()
    with patch.object(client, "detach_selected_device") as detach:
        tray.disconnect_menu.actions()[0].trigger()
        detach.assert_called_once()
        assert client.port_input.currentData() == 7
    with patch.object(client, "detach_all_devices") as detach_all:
        tray.disconnect_all_action.trigger()
        detach_all.assert_called_once()
    client._set_imported([])
    tray.rebuild_devices()
    assert not tray.disconnect_all_action.isEnabled()


def test_tray_blocks_operations_during_management(window):
    _, widget, _ = window
    tray = widget.tray
    assert widget.operation_gate.acquire(widget.management_tab)
    tray.rebuild_devices()
    assert not tray.refresh_action.isEnabled()
    assert not tray.share_menu.actions()[0].isEnabled()
    with patch.object(widget.client_tab, "detach_all_devices") as detach:
        tray.disconnect_all()
        detach.assert_not_called()
    widget.operation_gate.release(widget.management_tab)


def test_refresh_sequence_waits_for_each_operation(window):
    application, widget, _ = window
    tray = widget.tray
    calls = []
    def host_refresh():
        calls.append("host")
        widget.operation_gate.acquire(widget.host_tab)
    with patch.object(widget.host_tab, "refresh_usbipd_devices", side_effect=host_refresh), \
         patch.object(widget.client_tab, "refresh_imported_devices", side_effect=lambda: calls.append("client")):
        tray.refresh_devices()
        application.processEvents()
        application.processEvents()
        assert calls == ["host"]
        widget.operation_gate.release(widget.host_tab)
        application.processEvents()
        application.processEvents()
        assert calls == ["host", "client"]


def test_tray_result_notifies_once_and_logs_still_work(window):
    _, widget, _ = window
    tray = widget.tray
    with patch.object(tray.icon, "showMessage") as notify:
        tray._invoke(widget.host_tab, lambda: widget.host_tab.log("[OK] Bind completed."))
        widget.host_tab.log("[OK] List completed.")
        notify.assert_called_once()
        assert "Bind completed" in widget.host_tab.log_widget.toPlainText()


def test_missing_host_offers_configuration(window):
    _, widget, _ = window
    tray = widget.tray
    widget.client_tab.host_input.clear()
    tray.rebuild_devices()
    assert tray.connect_menu.actions()[0].text() == "Configure remote host..."
    tray.connect_menu.actions()[0].trigger()
    assert widget.centralWidget().currentWidget() is widget.client_tab



def test_automatic_refresh_defers_while_busy(window):
    _, widget, _ = window
    assert widget._periodic_refresh.interval() == 30000
    with patch.object(widget.tray, "refresh_devices") as refresh:
        widget._refresh_external_state()
        refresh.assert_called_once()
        widget.operation_gate.acquire(widget.management_tab)
        widget._refresh_external_state()
        refresh.assert_called_once()
        widget.operation_gate.release(widget.management_tab)



def test_automatic_refresh_logs_only_state_changes(window):
    from usbip_manager import UsbipDevice
    _, widget, _ = window
    host, tray = widget.host_tab, widget.tray
    host._set_devices([UsbipDevice("1-1", "Stick", state="Not shared")])
    before = host.log_widget.toPlainText()
    tray._start_quiet_refresh(host, "Host devices", lambda: host.log("[OK] Query completed."))
    tray._finish_quiet_refresh()
    assert host.log_widget.toPlainText() == before
    def changed():
        host.devices[0].state = "Shared"
        host.log("[OK] Query completed.")
    tray._start_quiet_refresh(host, "Host devices", changed)
    tray._finish_quiet_refresh()
    assert "Host devices updated" in host.log_widget.toPlainText()
    assert "Query completed" not in host.log_widget.toPlainText()


def test_automatic_refresh_deduplicates_errors_and_reports_recovery(window):
    _, widget, _ = window
    host, tray = widget.host_tab, widget.tray
    for _ in range(2):
        tray._start_quiet_refresh(host, "Host devices", lambda: host.log("[ERROR] Cannot query host."))
        tray._finish_quiet_refresh()
    assert host.log_widget.toPlainText().count("Cannot query host") == 1
    tray._start_quiet_refresh(host, "Host devices", lambda: host.log("[OK] Query completed."))
    tray._finish_quiet_refresh()
    assert "Connection restored" in host.log_widget.toPlainText()
    host.log("Manual action")
    assert "Manual action" in host.log_widget.toPlainText()



def test_preferences_restore_endpoint_size_and_splitter(window):
    application, widget, _ = window
    widget.client_tab.host_input.setText("my-host")
    widget.client_tab.tcp_port_input.setValue(4321)
    widget.resize(1200, 850)
    application.processEvents()
    widget.host_tab.splitter.setSizes([400, 180])
    expected_splitter = widget.host_tab.splitter.saveState()
    widget._save_preferences()
    widget.client_tab.host_input.setText("temporary")
    widget.client_tab.tcp_port_input.setValue(3240)
    widget.resize(1000, 700)
    widget.host_tab.splitter.setSizes([200, 300])
    widget._restore_preferences()
    assert widget.client_tab.host_input.text() == "my-host"
    assert widget.client_tab.tcp_port_input.value() == 4321
    assert widget.width() == 1200
    assert widget.height() == 850
    assert widget.host_tab.splitter.saveState() == expected_splitter


def test_invalid_preferences_use_defaults(window):
    _, widget, _ = window
    widget._settings.setValue("client/port", "invalid")
    widget._settings.setValue("window/width", -3)
    widget._settings.setValue("window/height", 99999999)
    widget._settings.setValue("host/splitter", "invalid")
    widget._restore_preferences()
    assert widget.client_tab.tcp_port_input.value() == 3240
    assert widget.size().width() == 1100
    assert widget.size().height() == 800



def test_background_query_keeps_controls_and_queues_manual_action(window):
    from usbip_manager import UsbipDevice
    application, widget, _ = window
    host, tray = widget.host_tab, widget.tray
    host._set_devices([UsbipDevice("1-1", "Stick", state="Not shared")])
    tray._start_quiet_refresh(host, "Host devices", lambda: widget.operation_gate.acquire(host))
    assert host.bind_btn.isEnabled()
    assert host.list_btn.isEnabled()
    assert widget.client_tab.refresh_imported_btn.isEnabled()
    with patch.object(host, "run_command") as run:
        host.bind_btn.click()
        run.assert_not_called()
        assert widget.operation_gate.pending_action is not None
        widget.operation_gate.release(host)
        tray._finish_quiet_refresh()
        for _ in range(5):
            application.processEvents()
        run.assert_called_once()



def test_about_available_from_window_and_tray(window):
    _, widget, _ = window
    widget.management_tab.about_btn.click()
    dialog = widget._about_dialog
    assert dialog.isVisible()
    dialog.close()
    widget.hide()
    widget.tray.about_action.trigger()
    assert widget.isVisible()
    assert widget._about_dialog is dialog
    assert dialog.isVisible()
    dialog.close()



def test_about_is_fixed_and_application_modal(window):
    from PyQt6.QtCore import Qt
    application, widget, _ = window
    widget.show_about()
    application.processEvents()
    dialog = widget._about_dialog
    assert application.activeModalWidget() is dialog
    assert dialog.windowModality() == Qt.WindowModality.ApplicationModal
    assert dialog.minimumSize() == dialog.maximumSize()
    assert not widget.tray.menu.isEnabled()
    dialog.reject()
    application.processEvents()
    assert widget.tray.menu.isEnabled()
    assert application.activeModalWidget() is None
