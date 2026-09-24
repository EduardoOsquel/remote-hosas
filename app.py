import subprocess
import sys
from typing import List, Optional

from PyQt6.QtCore import QSize, QSettings, QByteArray, pyqtSignal, QEvent, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QProgressDialog,
    QMessageBox,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

from operation_gate import OperationGate, defer_background_action
from host_commands import HostWorker
from management_ui import ManagementTab
from client_ui import ClientModeTab
from command_log import record_exception, record_result
from ui_theme import APP_STYLESHEET, DeviceStateDelegate, make_button, setup_page
from app_icon import application_icon, set_windows_app_id
from about_ui import AboutDialog
from device_presentation import ContentScrollArea, ActivityPanel, details_label, HOST_STATES
from ui_icons import line_icon, device_icon_kind
from system_tray import SystemTray

from joystick_bridge import JoystickPacket, JoystickState
from usbip_manager import (
    UsbipDevice,
    build_usbipd_bind_command,
    build_usbipd_unbind_command,
    parse_usbipd_list,
)


class HostModeTab(QWidget):
    activity = pyqtSignal(str)
    def __init__(self, gate=None) -> None:
        super().__init__()
        self.gate = gate or OperationGate()
        self._worker = None
        self.devices: List[UsbipDevice] = []
        self._log_buffer: List[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ContentScrollArea()
        scroll.setFrameShape(scroll.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        root = QVBoxLayout(content)
        setup_page(root)

        host_note = QLabel("Share USB devices physically connected to this Windows PC. Server: usbipd-win | TCP 3240. Sharing changes require administrator rights.")
        host_note.setWordWrap(True)
        root.addWidget(host_note)

        self.device_table = QTableWidget(0, 4)
        self.device_table.setHorizontalHeaderLabels(["BUSID", "VID:PID", "DEVICE", "STATE"])
        for column in range(4):
            alignment = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if column == 2 else Qt.AlignmentFlag.AlignCenter
            self.device_table.horizontalHeaderItem(column).setTextAlignment(alignment)
        self.device_table.setItemDelegateForColumn(3, DeviceStateDelegate(self.device_table))
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setSelectionBehavior(self.device_table.SelectionBehavior.SelectRows)
        self.device_table.setSelectionMode(self.device_table.SelectionMode.SingleSelection)
        self.device_table.setEditTriggers(self.device_table.EditTrigger.NoEditTriggers)
        self.device_table.setShowGrid(False)
        self.device_table.setWordWrap(False)
        self.device_table.verticalHeader().setDefaultSectionSize(38)
        header = self.device_table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(90)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.moveSection(header.visualIndex(2), 0)
        header.moveSection(header.visualIndex(3), 1)
        self.device_table.setColumnHidden(1, True)
        self.device_table.itemSelectionChanged.connect(self._update_controls)
        self.device_table.ensurePolished()
        self.device_table.setFixedHeight(self.device_table.horizontalHeader().sizeHint().height()
            + 5 * self.device_table.verticalHeader().defaultSectionSize() + 2 * self.device_table.frameWidth())
        self.device_panel = QWidget()
        device_layout = QVBoxLayout(self.device_panel)
        device_layout.setContentsMargins(0, 0, 0, 14)
        device_layout.setSpacing(10)
        self.device_count = QLabel("Local USB devices")
        device_layout.addWidget(self.device_count)
        device_layout.addWidget(self.device_table, 1)
        self.device_details = details_label()
        device_layout.addWidget(self.device_details)

        actions = QHBoxLayout()
        self.list_btn = self._make_button("List devices", "refresh")
        self.list_btn.clicked.connect(self.refresh_usbipd_devices)
        self.bind_btn = self._make_button("Share", "share")
        self.bind_btn.setToolTip("Share this device (usbipd bind). Requires administrator approval.")
        self.bind_btn.clicked.connect(self.bind_selected_device)
        self.unbind_btn = self._make_button("Stop sharing", "disconnect")
        self.unbind_btn.setToolTip("Stop sharing this device (usbipd unbind). An active client will lose access.")
        self.unbind_btn.clicked.connect(self.unbind_selected_device)
        actions.addWidget(self.list_btn)
        actions.addWidget(self.bind_btn)
        actions.addWidget(self.unbind_btn)
        actions.addStretch(1)
        self.list_btn.setProperty("primary", True)
        device_layout.addLayout(actions)

        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setPlaceholderText("Host logs...")
        self.activity_panel = ActivityPanel(self.log_widget)
        log_panel = self.activity_panel
        self.log_widget.setMinimumHeight(100)
        root.addWidget(self.device_panel)
        root.addWidget(log_panel)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)


        self.gate.changed.connect(self._update_controls)
        self._update_controls()
        QTimer.singleShot(0, self.refresh_usbipd_devices)

    def showEvent(self, event):
        super().showEvent(event)
        self.device_table.setFixedHeight(self.device_table.horizontalHeader().sizeHint().height()
            + 5 * self.device_table.verticalHeader().defaultSectionSize()
            + 2 * self.device_table.frameWidth())

    _make_button = staticmethod(make_button)

    def log(self, message: str) -> None:
        if getattr(self, "_silent_logs", None) is not None:
            self._silent_logs.append(message)
            return
        self.activity_panel.update_message(message)
        self.activity.emit(message)
        self._log_buffer.append(message)
        if len(self._log_buffer) > 250:
            self._log_buffer = self._log_buffer[-250:]
        self.log_widget.setPlainText("\n".join(self._log_buffer))
        self.log_widget.verticalScrollBar().setValue(self.log_widget.verticalScrollBar().maximum())

    @property
    def is_busy(self):
        return self._worker is not None

    def _update_controls(self):
        if self.gate.background:
            return
        idle = not self.is_busy and self.gate.available(self)
        self.list_btn.setEnabled(idle)
        self.device_table.setEnabled(idle and bool(self.devices))
        index = self.selected_index()
        state = self.devices[index].state if 0 <= index < len(self.devices) else None
        if state is not None:
            device = self.devices[index]
            self.device_details.setText(f"{device.name}\n{HOST_STATES.get(state, state)}\n"
                f"BUSID: {device.busid} | VID:PID: {device.vid_pid or '-'} | Source: This PC")
        else:
            self.device_details.setText("Select a device to see its details.")
        self.bind_btn.setEnabled(idle and state == "Not shared")
        self.unbind_btn.setEnabled(idle and state in {"Shared", "Shared (forced)", "Attached"})

    def run_command(self, label, command, refresh=False):
        if self.is_busy or not self.gate.acquire(self):
            self.log("Wait for the current USB/IP or management action to finish.")
            return
        self._start_host_command(label, command, refresh)

    def _start_host_command(self, label, command, refresh):
        self.log(f"> {label}")
        if refresh:
            self.log("Administrator approval may be requested. Cancelling leaves sharing unchanged.")
        worker = HostWorker(command, self)
        self._worker = worker
        self._update_controls()
        worker.finished.connect(lambda: self._host_finished(worker, label, command, refresh))
        worker.start()

    def _host_finished(self, worker, label, command, refresh):
        result = worker.result
        if worker.error is not None:
            self.log(record_exception(label, command, worker.error))
            if isinstance(worker.error, subprocess.TimeoutExpired):
                self.log("The host command timed out after 30 seconds. Refresh to check its actual state.")
        else:
            self.log(record_result(label, command, result.returncode, result.stdout, result.stderr))
            if result.returncode == 1223:
                self.log("Administrator approval was cancelled. No sharing change was requested.")
            elif result.returncode == 1460:
                self.log("The host command timed out after 30 seconds. Checking actual sharing state.")
        if not refresh:
            if worker.error is None and result.returncode == 0:
                self._set_devices(parse_usbipd_list(result.stdout))
                shared = sum(d.state in {"Shared", "Shared (forced)", "Attached"} for d in self.devices)
                self.log(f"Shared host devices: {shared}. Sharing remains enabled when this application exits.")
            else:
                self._set_devices([], "Unable to list devices")
        self._worker = None
        worker.deleteLater()
        if refresh:
            self._start_host_command("List USB devices", ["usbipd", "list"], False)
        else:
            self.gate.release(self)
            self._update_controls()

    def selected_index(self):
        return self.device_table.currentRow() if self.device_table.selectedItems() else -1

    def selected_busid(self):
        index = self.selected_index()
        return self.devices[index].busid if 0 <= index < len(self.devices) else None

    def select_busid(self, busid):
        for index, device in enumerate(self.devices):
            if device.busid == busid:
                self.device_table.selectRow(index)
                return True
        return False

    def _set_devices(self, devices: List[UsbipDevice], empty_text: str = "No USB devices detected") -> None:
        if self.gate.background and self.devices == devices:
            return
        previous = self.selected_busid()
        self.devices = devices
        self.device_table.blockSignals(True)
        self.device_table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            for column, value in enumerate((device.busid, device.vid_pid or "-",
                                            device.name or "Unknown device", device.state or "Not shared")):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if column == 2 else Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(HOST_STATES.get(value, value) if column == 3 else value)
                if column == 2:
                    item.setIcon(line_icon(device_icon_kind(device.name)))
                self.device_table.setItem(row, column, item)
        if devices:
            index = next((i for i, d in enumerate(devices) if d.busid == previous), 0)
            self.device_table.selectRow(index)
        self.device_table.blockSignals(False)
        self._update_controls()
        self.device_count.setText(f"Local USB devices - {len(devices)} detected" if devices else empty_text)

    @defer_background_action
    def refresh_usbipd_devices(self):
        self.run_command("List USB devices", ["usbipd", "list"])

    @defer_background_action
    def bind_selected_device(self) -> None:
        idx = self.selected_index()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Warning", "Select a device from the list.")
            return
        if self.devices[idx].state != "Not shared":
            return
        busid = self.devices[idx].busid
        self.run_command(f"Bind device {busid}", build_usbipd_bind_command(busid), refresh=True)

    @defer_background_action
    def unbind_selected_device(self) -> None:
        idx = self.selected_index()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Warning", "Select a device from the list.")
            return
        if self.devices[idx].state not in {"Shared", "Shared (forced)", "Attached"}:
            return
        busid = self.devices[idx].busid
        self.run_command(f"Unbind device {busid}", build_usbipd_unbind_command(busid), refresh=True)


from joystick_tools import JoystickTools


class JoystickTab(JoystickTools, QWidget):
    _make_button = staticmethod(make_button)

    def __init__(self) -> None:
        super().__init__()
        self._devices: List[str] = []
        self._current_joystick: Optional[object] = None
        self._timer: Optional[QTimer] = None
        self._log_buffer: List[str] = []

        root = QVBoxLayout(self)
        setup_page(root)

        note = QLabel("Local controller monitor. Attach a remote device in Client Mode first, then refresh controllers here.")
        note.setWordWrap(True)
        root.addWidget(note)
        panel = QGroupBox("Local controller")
        form = QFormLayout(panel)
        self.device_combo = QComboBox()
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setMinimumContentsLength(24)
        self.device_combo.addItem("No joysticks detected")
        form.addRow("Local joystick:", self.device_combo)
        self.device_details = QLabel("No controller selected")
        self.device_details.setWordWrap(True)
        self.device_details.setTextFormat(Qt.TextFormat.PlainText)
        self.device_details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Controller details:", self.device_details)
        self.device_combo.currentIndexChanged.connect(self._show_device_details)
        hint = QLabel("SDL indices are local to this monitor and may differ from game numbering. "
                      "Hardware GUIDs can be identical for controllers of the same model.")
        hint.setWordWrap(True)
        form.addRow(hint)
        root.addWidget(panel)
        self.monitor_status = QLabel("Not monitoring")
        root.addWidget(self.monitor_status)

        self.connect_btn = self._make_button("Start monitoring", "connect")
        self.connect_btn.clicked.connect(self.connect_local_joystick)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Joystick logs...")

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.connect_btn)
        refresh_btn = make_button("Refresh controllers", "refresh")
        refresh_btn.clicked.connect(self.refresh_devices)
        buttons_row.addWidget(refresh_btn)
        buttons_row.addStretch(1)
        root.addLayout(buttons_row)
        self.live_state = QTextEdit()
        self.live_state.setReadOnly(True)
        self.live_state.setPlaceholderText("Start monitoring to see live axes, buttons and hats.")
        root.addWidget(QLabel("Live state"))
        root.addWidget(self.live_state, 2)
        root.addWidget(QLabel("Joystick activity"))
        root.addWidget(self.log, 1)

        self._pygame = pygame
        self.setup_tools(form, root, buttons_row, QSettings("RemoteHosas", "USBIPBridge"))
        self.refresh_devices()

    def log_message(self, text: str) -> None:
        self._log_buffer.append(text)
        if len(self._log_buffer) > 200:
            self._log_buffer = self._log_buffer[-200:]
        self.log.setPlainText("\n".join(self._log_buffer))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def stop_monitoring(self, *, announce=True):
        if self._timer is not None:
            self._timer.stop()
        joystick = self._current_joystick
        self._current_joystick = None
        if joystick is not None:
            try:
                joystick.quit()
            except pygame.error:
                pass
        self.connect_btn.setText("Start monitoring")
        self.device_combo.setEnabled(True)
        self.monitor_status.setText("Not monitoring")
        if announce and joystick is not None:
            self.log_message("Monitoring stopped.")

    def _show_device_details(self):
        info = self.device_combo.currentData()
        self.device_details.setText(info["details"] if info else "No controller selected")
        self.show_alias()

    def refresh_devices(self) -> None:
        self.cancel_identification()
        self.stop_monitoring(announce=False)
        self._devices = []
        self.device_combo.clear()
        self.live_state.setPlainText("")
        self.connect_btn.setEnabled(False)
        if pygame is None:
            self.identify_btn.setEnabled(False)
            self.device_combo.addItem("PyGame not installed")
            self.log_message("PyGame is not installed. Install it with: pip install pygame PyQt6")
            return
        try:
            pygame.init()
            pygame.joystick.init()
            pygame.event.pump()
            for idx in range(pygame.joystick.get_count()):
                joystick = None
                try:
                    joystick = pygame.joystick.Joystick(idx)
                    joystick.init()
                    name = joystick.get_name()
                    instance = joystick.get_instance_id()
                    details = (f"SDL index: {idx} | Session instance: {instance}\n"
                               f"Hardware GUID: {joystick.get_guid()}\n"
                               f"Axes: {joystick.get_numaxes()} | Buttons: {joystick.get_numbuttons()} | "
                               f"Hats: {joystick.get_numhats()} | Power: {joystick.get_power_level()}")
                    self._devices.append(name)
                    self.device_combo.addItem(f"{idx} - {name}",
                        {"index": idx, "instance": instance, "details": details,
                         "name": name, "guid": joystick.get_guid()})
                except pygame.error:
                    self.log_message(f"Controller {idx} became unavailable. Refresh to try again.")
                finally:
                    if joystick is not None:
                        try:
                            joystick.quit()
                        except pygame.error:
                            pass
        except pygame.error as exc:
            self.log_message(f"Unable to enumerate controllers: {exc}")
        if not self._devices:
            self.device_combo.addItem("No joysticks detected")
        self.connect_btn.setEnabled(bool(self._devices))
        self.prepare_aliases()
        self._show_device_details()
        self.log_message(f"Detected {len(self._devices)} joystick(s).")

    def connect_local_joystick(self) -> None:
        if self._current_joystick is not None:
            self.stop_monitoring()
            return
        info = self.device_combo.currentData()
        if pygame is None or not info:
            return
        try:
            joystick = pygame.joystick.Joystick(info["index"])
            self._current_joystick = joystick
            joystick.init()
            if joystick.get_instance_id() != info["instance"]:
                raise pygame.error("Controller order changed")
        except pygame.error:
            self._disconnect_monitor()
            return
        self.monitor_status.setText("Monitoring")
        self.connect_btn.setText("Stop monitoring")
        self.device_combo.setEnabled(False)
        self.log_message(f"Monitoring {self.device_combo.currentText()}.")
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.read_joystick_state)
        self._timer.start(20)

    def _disconnect_monitor(self):
        self.stop_monitoring(announce=False)
        self.connect_btn.setEnabled(False)
        self.monitor_status.setText("Disconnected")
        self.log_message("Disconnected. Refresh controllers before starting monitoring again.")

    def read_joystick_state(self) -> None:
        if self._current_joystick is None:
            return

        joystick = self._current_joystick
        try:
            pygame.event.pump()
            for event in pygame.event.get([pygame.JOYDEVICEREMOVED]):
                if event.instance_id == joystick.get_instance_id():
                    raise pygame.error("Controller removed")
            axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
            buttons = [bool(joystick.get_button(i)) for i in range(joystick.get_numbuttons())]
            hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]
        except pygame.error:
            self._disconnect_monitor()
            return

        self.render_indicators(axes, buttons, hats)
        state = JoystickState(axes=axes, buttons=buttons, hats=hats)
        text = ("Axes: " + " | ".join(f"{i}: {value:+.3f}" for i, value in enumerate(state.axes))
                + "\nPressed buttons (0-based): " + (", ".join(str(i) for i, pressed in enumerate(state.buttons) if pressed) or "None")
                + "\nHats: " + " | ".join(f"{i}: {value}" for i, value in enumerate(state.hats)))
        if self.live_state.toPlainText() != text:
            self.live_state.setPlainText(text)


class UsbipJoystickBridgeApp(QMainWindow):
    def __init__(self, settings=None) -> None:
        super().__init__()
        self._exit_requested = False
        self._shutdown_pending = False
        self._shutdown_ready = False
        self._shutdown_generation = 0
        self._shutdown_cleanup_started = False
        self._exit_progress = None
        self._exit_timeout = QTimer(self)
        self._exit_timeout.setSingleShot(True)
        self._exit_timeout.timeout.connect(self._cancel_exit)
        self.setWindowTitle("USB/IP + Joystick Bridge")
        self.setWindowIcon(application_icon())
        self.resize(1100, 800)
        self.setStyleSheet(APP_STYLESHEET)
        self.setMinimumSize(900, 680)

        tabs = QTabWidget()
        self.operation_gate = OperationGate()
        self.host_tab = HostModeTab(self.operation_gate)
        tabs.setIconSize(QSize(18, 18))
        tabs.addTab(self.host_tab, line_icon("share"), "Host Mode")
        self.client_tab = ClientModeTab(self.operation_gate)
        tabs.addTab(self.client_tab, line_icon("connect"), "Client Mode")
        self.management_tab = ManagementTab(self.operation_gate)
        tabs.addTab(self.management_tab, line_icon("settings"), "Management")
        self.joystick_tab = JoystickTab()
        tabs.addTab(self.joystick_tab, line_icon("gaming"), "Joystick")
        self.setCentralWidget(tabs)
        self.management_tab.about_btn.clicked.connect(self.show_about)
        self._about_dialog = None
        self.tray = SystemTray(self)
        self._foreground_refresh = QTimer(self)
        self._foreground_refresh.setSingleShot(True)
        self._foreground_refresh.setInterval(1000)
        self._foreground_refresh.timeout.connect(self._refresh_external_state)
        tabs.currentChanged.connect(self._active_page_changed)
        self._periodic_refresh = QTimer(self)
        self._periodic_refresh.setInterval(30000)
        self._periodic_refresh.timeout.connect(self._refresh_external_state)
        self._periodic_refresh.start()
        self._settings = settings if settings is not None else QSettings("RemoteHosas", "USBIPBridge")
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_preferences)
        self._restore_preferences()
        self.client_tab.host_input.textChanged.connect(self._schedule_save)
        self.client_tab.tcp_port_input.valueChanged.connect(self._schedule_save)

    def show_about(self):
        if self._about_dialog is None:
            self._about_dialog = AboutDialog(self)
            self._about_dialog.finished.connect(lambda: self.tray.menu.setEnabled(True))
        self.tray.menu.setEnabled(False)
        self._about_dialog.show()
        self._about_dialog.raise_()
        self._about_dialog.activateWindow()

    def _restore_preferences(self):
        host = self._settings.value("client/host", "")
        self.client_tab.host_input.setText(host if isinstance(host, str) else "")
        def integer(key, default, low, high):
            try:
                value = int(self._settings.value(key, default))
                return value if low <= value <= high else default
            except (ValueError, TypeError, OverflowError):
                return default
        self.client_tab.tcp_port_input.setValue(integer("client/port", 3240, 1024, 65535))
        self.resize(integer("window/width", 1100, 900, 16000),
                    integer("window/height", 800, 680, 16000))

        maximized = str(self._settings.value("window/maximized", "false")).lower() == "true"
        self.tray.restore_maximized = maximized
        if maximized:
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

    def _schedule_save(self, *args):
        if hasattr(self, "_save_timer"):
            self._save_timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_save()

    def _save_preferences(self):
        self._save_timer.stop()
        self._settings.setValue("client/host", self.client_tab.host_input.text().strip())
        self._settings.setValue("client/port", self.client_tab.tcp_port_input.value())
        normal = self.normalGeometry() if self.isMaximized() or self.isMinimized() else self.geometry()
        if normal.isValid():
            self._settings.setValue("window/width", normal.width())
            self._settings.setValue("window/height", normal.height())
        self._settings.setValue("window/maximized", self.tray.restore_maximized if self.isMinimized() else self.isMaximized())
        self._settings.sync()
        if self._settings.status() != QSettings.Status.NoError:
            self.statusBar().showMessage("Unable to save preferences. Check your user profile permissions.", 8000)


    def _active_page_changed(self, *args):
        if self.tray.remote_poll_visible():
            self._foreground_refresh.start()
        elif (self.operation_gate.background
              and getattr(self.client_tab, "_label", None) == "List remote devices"):
            self.client_tab.cancel_background_query()

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, "_foreground_refresh"):
            self._active_page_changed()

    def _refresh_external_state(self):
        if self.tray._idle() and not self.tray._refresh_steps:
            self.management_tab.refresh_installation_status()
            self.tray.refresh_devices(automatic=True)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if (event.type() == QEvent.Type.ActivationChange and self.isActiveWindow()
                and hasattr(self, "_foreground_refresh")):
            self._foreground_refresh.start()
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "tray"):
            self._schedule_save()
            if self.isMinimized():
                self.tray.restore_maximized = bool(event.oldState() & Qt.WindowState.WindowMaximized)
                QTimer.singleShot(0, self._minimize_to_tray)

    def _minimize_to_tray(self):
        if self.isMinimized():
            self.tray.hide_window()

    def request_exit(self):
        self._exit_requested = True
        self.close()

    def closeEvent(self, event) -> None:
        self._save_preferences()
        if self._shutdown_ready:
            self.tray.icon.hide()
            event.accept()
            QApplication.instance().quit()
            return
        if self._shutdown_pending:
            if self._exit_progress is not None:
                self._exit_progress.show()
                self._exit_progress.raise_()
            self._exit_requested = False
            event.ignore()
            return
        choice = "exit" if self._exit_requested else self.tray.choose_close_action()
        self._exit_requested = False
        if choice != "exit":
            event.ignore()
            if choice == "tray":
                self.tray.hide_window()
            return
        if self.host_tab.is_busy and not self.operation_gate.background:
            self.tray.restore()
            self.centralWidget().setCurrentWidget(self.host_tab)
            self.host_tab.log("Wait for the current host action to finish before closing.")
            event.ignore()
            return
        if self.client_tab.is_busy and not self.operation_gate.background:
            self.tray.restore()
            self.centralWidget().setCurrentWidget(self.client_tab)
            self.client_tab.log("Wait for the current client action to finish before closing.")
            event.ignore()
            return
        if self.management_tab.is_busy:
            self.tray.restore()
            self.centralWidget().setCurrentWidget(self.management_tab)
            self.management_tab.operation_status.setText(
                "An action is still running. Wait for it to finish before closing.")
            event.ignore()
            return
        event.ignore()
        self._shutdown_pending = True
        self._shutdown_generation += 1
        self._shutdown_cleanup_started = False
        self.operation_gate.shutting_down = True
        self.operation_gate.pending_action = None
        self.operation_gate.prioritize_manual_action()
        self._periodic_refresh.stop()
        self._foreground_refresh.stop()
        self.tray._refresh_steps.clear()
        self.tray._automatic_cycle = False
        self.tray._notification_source = None
        self.joystick_tab.cancel_identification()
        if self.joystick_tab._timer is not None:
            self.joystick_tab._timer.stop()
        self.tray.restore()
        self.centralWidget().setCurrentWidget(self.client_tab)
        self.centralWidget().setEnabled(False)
        if self._exit_progress is None:
            self._exit_progress = QProgressDialog("Preparing to disconnect devices...", "Cancel exit", 0, 0, self)
            self._exit_progress.setWindowTitle("Closing application")
            self._exit_progress.setMinimumDuration(0)
            self._exit_progress.canceled.connect(self._cancel_exit)
            self.client_tab.activity.connect(self._exit_activity)
        self._exit_progress.setLabelText("Waiting for the current status check to finish...")
        self._exit_progress.show()
        self._exit_timeout.start(100000)
        self._continue_exit(self._shutdown_generation)

    def _exit_activity(self, message):
        if self._shutdown_pending and self._exit_progress is not None:
            self._exit_progress.setLabelText(message)

    def _continue_exit(self, generation):
        if not self._shutdown_pending or generation != self._shutdown_generation:
            return
        if self.host_tab.is_busy or self.client_tab.is_busy or self.operation_gate.owner is not None:
            QTimer.singleShot(100, lambda: self._continue_exit(generation))
            return
        if self.tray._quiet_refresh is not None:
            self.tray._finish_quiet_refresh()
        self._shutdown_cleanup_started = True
        self._exit_progress.setLabelText("Checking and disconnecting imported devices...")
        def done(success):
            if self._shutdown_pending and generation == self._shutdown_generation:
                self._finish_exit(success)
        try:
            self.client_tab.disconnect_before_exit(done)
        except Exception as error:
            self.client_tab.log(record_exception("Disconnect before exit", ["usbip"], error))
            done(False)

    def _cancel_exit(self):
        if not self._shutdown_pending:
            return
        self._shutdown_generation += 1
        if self._shutdown_cleanup_started and self.client_tab.is_busy:
            self.client_tab._callback = None
            self.client_tab._after = None
            self.client_tab._on_failure = None
            self.client_tab._timeout()
        self._finish_exit(False)

    def _finish_exit(self, success):
        self._exit_timeout.stop()
        if self._exit_progress is not None:
            self._exit_progress.hide()
        self.operation_gate.shutting_down = False
        self._shutdown_pending = False
        self.centralWidget().setEnabled(True)
        if success:
            self._save_preferences()
            self._shutdown_ready = True
            self.tray.icon.hide()
            self.hide()
            QApplication.instance().quit()
        else:
            self._periodic_refresh.start()
            self.tray.restore()
            self.centralWidget().setCurrentWidget(self.client_tab)
            self.client_tab.log("Exit cancelled: USB/IP devices could not be confirmed disconnected. Refresh connections and retry Exit.")


def main() -> None:
    set_windows_app_id()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setWindowIcon(application_icon())
    window = UsbipJoystickBridgeApp()
    window.show()
    def refresh_client_when_idle():
        if window.operation_gate.owner is not None:
            QTimer.singleShot(100, refresh_client_when_idle)
        else:
            window.client_tab.refresh_imported_devices()
    QTimer.singleShot(0, refresh_client_when_idle)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
