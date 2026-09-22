"""Tray lifetime and close choices; hiding never stops background work."""

import sys
import logging
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtGui import QCursor
from app_icon import APP_NAME
from ui_icons import line_icon, device_icon_kind
from PyQt6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon


class SystemTray(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.restore_maximized = False
        self.icon = QSystemTrayIcon(window.windowIcon(), self)
        self.icon.setToolTip("USB/IP + Joystick Bridge")
        self._native_open = False
        self._native_menu = None
        if sys.platform == "win32":
            from native_tray_menu import WindowsMenu
            self._native_menu = WindowsMenu()
        self.menu = QMenu(window)
        self.show_action = self.menu.addAction("Show application")
        self.show_action.triggered.connect(self.restore)
        self.tabs_menu = self.menu.addMenu("Open tab")
        for label, tab in (("Host Mode", window.host_tab), ("Client Mode", window.client_tab),
                           ("Management", window.management_tab), ("Joystick", window.joystick_tab)):
            action = self.tabs_menu.addAction(label)
            action.triggered.connect(lambda checked=False, tab=tab: self.open_tab(tab))
        self.menu.addSeparator()
        self.share_menu = self.menu.addMenu("Share device")
        self.unshare_menu = self.menu.addMenu("Stop sharing")
        self.connect_menu = self.menu.addMenu("Connect device")
        self.disconnect_menu = self.menu.addMenu("Disconnect device")
        self.disconnect_all_action = self.menu.addAction("Disconnect all")
        self.disconnect_all_action.triggered.connect(self.disconnect_all)
        self.refresh_action = self.menu.addAction("Refresh devices")
        self.refresh_action.triggered.connect(self.refresh_devices)
        self._automatic_cycle = False
        self._refresh_steps = []
        self._quiet_refresh = None
        self._refresh_errors = {}
        self._notification_source = None
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._update)
        window.operation_gate.changed.connect(lambda: self._update_timer.start(0))
        window.host_tab.activity.connect(lambda message: self._activity(window.host_tab, message))
        window.client_tab.activity.connect(lambda message: self._activity(window.client_tab, message))
        self.menu.aboutToShow.connect(lambda: self.rebuild_devices(force=True))
        for popup in (self.menu, self.tabs_menu, self.share_menu, self.unshare_menu,
                      self.connect_menu, self.disconnect_menu):
            popup.aboutToHide.connect(lambda: self._update_timer.start(0))
        self.menu.addSeparator()
        self.about_action = self.menu.addAction("About")
        self.about_action.triggered.connect(self.show_about)
        self.exit_action = self.menu.addAction("Exit application")
        self.exit_action.triggered.connect(window.request_exit)
        if self._native_menu is None:
            self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self.rebuild_devices()
        if self.available():
            self.icon.show()

    def show_about(self):
        self.restore()
        self.window.show_about()

    def open_tab(self, tab):
        self.window.centralWidget().setCurrentWidget(tab)
        self.restore()

    def _idle(self):
        return (self.window.operation_gate.owner is None
                and not self.window._shutdown_pending
                and not self.window._shutdown_ready
                and not any(tab.is_busy for tab in (self.window.host_tab,
                           self.window.client_tab, self.window.management_tab)))

    def _update(self):
        if self._quiet_refresh is not None and self._idle():
            self._finish_quiet_refresh()
        if self._refresh_steps and self._idle():
            action = self._refresh_steps.pop(0)
            action()
            self._update_timer.start(0)
        if not self._refresh_steps and self._idle():
            self._automatic_cycle = False
        self.rebuild_devices()

    @staticmethod
    def _placeholder(menu, text):
        menu.addAction(text).setEnabled(False)

    @staticmethod
    def _device_action(menu, label, callback, device_name=None):
        action = menu.addAction(label.replace("&", "&&"))
        if device_name is not None:
            action.setIcon(line_icon(device_icon_kind(device_name)))
        action.triggered.connect(lambda checked=False: callback())

    def rebuild_devices(self, *, force=False):
        if self._native_open:
            return
        # Do not destroy actions beneath the pointer while a popup is open.
        # Device actions revalidate their identifiers and the operation gate.
        if not force and any(popup.isVisible() for popup in
                (self.menu, self.tabs_menu, self.share_menu, self.unshare_menu,
                 self.connect_menu, self.disconnect_menu)):
            return
        if self.window.operation_gate.background or self._automatic_cycle:
            return
        host, client = self.window.host_tab, self.window.client_tab
        idle = self._idle() and not self._refresh_steps
        for menu in (self.share_menu, self.unshare_menu, self.connect_menu, self.disconnect_menu):
            menu.clear()
        if not idle:
            for menu in (self.share_menu, self.unshare_menu, self.connect_menu, self.disconnect_menu):
                self._placeholder(menu, "Loading..." if self._refresh_steps else "An operation is in progress...")
        else:
            for device in host.devices:
                if device.state == "Not shared":
                    menu, share = self.share_menu, True
                elif device.state in {"Shared", "Shared (forced)", "Attached"}:
                    menu, share = self.unshare_menu, False
                else:
                    continue
                self._device_action(menu, f"{device.busid} - {device.name}",
                    lambda busid=device.busid, share=share: self.share_device(busid, share), device.name)
            endpoint = client._endpoint()
            if not endpoint[0]:
                self._device_action(self.connect_menu, "Configure remote host...",
                                    lambda: self.open_tab(client))
            elif client._listed_endpoint != endpoint:
                self._device_action(self.connect_menu, "List remote devices...", self.refresh_devices)
            else:
                self._placeholder(self.connect_menu, f"Host: {endpoint[0]}:{endpoint[1]}")
                for device in client.devices:
                    self._device_action(self.connect_menu, f"{device.busid} - {device.name}",
                        lambda busid=device.busid, endpoint=endpoint: self.connect_device(busid, endpoint), device.name)
                if not client.devices:
                    self._placeholder(self.connect_menu, "No devices available")
            for device in client.imported_devices:
                self._device_action(self.disconnect_menu,
                    f"Port {device.port} - {device.name} - {device.location}",
                    lambda port=device.port, location=device.location: self.disconnect_device(port, location), device.name)
            for menu in (self.share_menu, self.unshare_menu, self.disconnect_menu):
                if not menu.actions():
                    self._placeholder(menu, "No devices available")
        self.disconnect_all_action.setEnabled(idle and bool(client.imported_devices))
        self.refresh_action.setEnabled(idle)

    def _invoke(self, source, action):
        gate = self.window.operation_gate
        if gate.background:
            if gate.pending_action is None:
                def retry():
                    if gate.pending_action is not retry or gate.shutting_down:
                        return
                    if gate.background or not self._idle():
                        QTimer.singleShot(25, retry)
                        return
                    gate.pending_action = None
                    self._invoke(source, action)
                gate.pending_action = retry
                gate.prioritize_manual_action()
                QTimer.singleShot(0, retry)
            return
        if not self._idle() or self._refresh_steps:
            return
        self._notification_source = source
        action()
        self._update_timer.start(0)

    def _activity(self, source, message):
        if source is self._notification_source and message.startswith(("[OK]", "[ERROR]")):
            self._notification_source = None
            error = message.startswith("[ERROR]")
            self.icon.showMessage(APP_NAME, message,
                QSystemTrayIcon.MessageIcon.Warning if error else QSystemTrayIcon.MessageIcon.Information)
        self._update_timer.start(0)

    def share_device(self, busid, share):
        host = self.window.host_tab
        expected = {"Not shared"} if share else {"Shared", "Shared (forced)", "Attached"}
        if not any(d.busid == busid and d.state in expected for d in host.devices):
            return
        def action():
            host.device_combo.setCurrentIndex(host.device_combo.findData(busid))
            (host.bind_selected_device if share else host.unbind_selected_device)()
        self._invoke(host, action)

    def connect_device(self, busid, endpoint):
        client = self.window.client_tab
        if endpoint != client._endpoint() or endpoint != client._listed_endpoint:
            return
        index = client.device_combo.findData(busid)
        if index < 0:
            return
        def action():
            client.device_combo.setCurrentIndex(index)
            client.attach_selected_device()
        self._invoke(client, action)

    def disconnect_device(self, port, location):
        client = self.window.client_tab
        if not any(d.port == port and d.location == location for d in client.imported_devices):
            return
        def action():
            client.port_input.setCurrentIndex(client.port_input.findData(port))
            client.detach_selected_device()
        self._invoke(client, action)

    def disconnect_all(self):
        client = self.window.client_tab
        if client.imported_devices:
            self._invoke(client, client.detach_all_devices)

    @staticmethod
    def _snapshot(tab, scope):
        devices = tab.imported_devices if scope == "Imported devices" else tab.devices
        return tuple(sorted(repr(device) for device in devices))

    def _start_quiet_refresh(self, tab, scope, action):
        if scope == "Remote devices" and not self.remote_poll_visible():
            return
        self._quiet_refresh = (tab, scope, self._snapshot(tab, scope))
        tab._silent_logs = []
        gate = self.window.operation_gate
        gate.background = True
        gate.starting_background = True
        try:
            action()
        finally:
            gate.starting_background = False

    def _finish_quiet_refresh(self):
        tab, scope, before = self._quiet_refresh
        messages = tab._silent_logs
        tab._silent_logs = None
        self._quiet_refresh = None
        gate = self.window.operation_gate
        gate.background = False
        if gate.pending_action is not None:
            self._refresh_steps.clear()
        gate.changed.emit()
        after = self._snapshot(tab, scope)
        errors = tuple(message for message in messages if message.startswith("[ERROR]"))
        previous_errors = self._refresh_errors.get(scope, ())
        self._refresh_errors[scope] = errors
        if errors:
            if errors != previous_errors:
                for message in errors:
                    tab.log(message)
        elif before != after or previous_errors:
            tab.log(f"{scope} updated - {len(after)} device(s) detected." +
                    (" Connection restored." if previous_errors else ""))

    def remote_poll_visible(self):
        return (self.window.isVisible() and not self.window.isMinimized()
                and self.window.centralWidget().currentWidget() is self.window.client_tab)

    def refresh_devices(self, checked=False, *, automatic=False):
        if not self._idle() or self._refresh_steps:
            return
        self._automatic_cycle = automatic
        client = self.window.client_tab
        steps = [(self.window.host_tab, "Host devices", self.window.host_tab.refresh_usbipd_devices),
                 (client, "Imported devices", client.refresh_imported_devices)]
        if client._endpoint()[0] and (not automatic or self.remote_poll_visible()):
            steps.append((client, "Remote devices", client.refresh_remote_devices))
        self._refresh_steps = [
            (lambda tab=tab, scope=scope, action=action: self._start_quiet_refresh(tab, scope, action))
            if automatic else action for tab, scope, action in steps]
        self._update_timer.start(0)
        self.rebuild_devices()

    def available(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def hide_window(self):
        if not self.available():
            return False
        if not self.window.isMinimized():
            self.restore_maximized = self.window.isMaximized()
        self.icon.show()
        self.window.hide()
        return True

    def restore(self):
        if self.restore_maximized:
            self.window.showMaximized()
        else:
            self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _show_native_menu(self):
        if self._native_open or not self.menu.isEnabled():
            return
        self.rebuild_devices(force=True)
        self._native_open = True
        selected = None
        try:
            selected = self._native_menu.show(self.menu)
        except OSError:
            logging.getLogger(__name__).exception("Native tray menu failed; using Qt fallback")
            self.menu.popup(QCursor.pos())
        finally:
            self._native_open = False
        if selected is not None and selected.isEnabled():
            selected.trigger()
        self._update_timer.start(0)

    def _activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Context and self._native_menu is not None:
            self._show_native_menu()
            return
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore()

    def choose_close_action(self):
        dialog = QMessageBox(self.window)
        dialog.setWindowTitle("Close application")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("Keep the application running in the system tray, or exit completely?")
        dialog.setInformativeText(
            "System tray keeps background actions and controller monitoring running. "
            "Exit disconnects all imported USB/IP devices before closing. Devices shared in Host Mode stay shared.")
        tray = dialog.addButton("Send to System Tray", QMessageBox.ButtonRole.ActionRole)
        tray.setEnabled(self.available())
        exit_button = dialog.addButton("Exit application", QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(tray if self.available() else cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is tray:
            return "tray"
        if dialog.clickedButton() is exit_button:
            return "exit"
        return "cancel"
