import subprocess
import sys
from typing import List, Optional

from PyQt6.QtCore import pyqtSignal, QEvent, Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
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

from operation_gate import OperationGate
from host_commands import HostWorker
from management_ui import ManagementTab
from client_ui import ClientModeTab
from command_log import record_exception, record_result
from ui_theme import APP_STYLESHEET, DeviceStateDelegate, make_button, setup_page
from app_icon import application_icon, set_windows_app_id
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

        root = QVBoxLayout(self)
        setup_page(root)

        host_note = QLabel("Share USB devices physically connected to this Windows PC. Server: usbipd-win | TCP 3240. Bind / Unbind require administrator rights.")
        host_note.setWordWrap(True)
        root.addWidget(host_note)

        self.device_combo = QComboBox()
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setMinimumContentsLength(24)
        self.device_combo.addItem("No shared USB devices")
        root.addWidget(QLabel("Selected USB device"))
        root.addWidget(self.device_combo)

        self.device_table = QTableWidget(0, 4)
        self.device_table.setHorizontalHeaderLabels(["BUSID", "VID:PID", "DEVICE", "STATE"])
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
        self.device_table.itemSelectionChanged.connect(self._select_table_device)
        self.device_combo.currentIndexChanged.connect(self._select_combo_device)
        self.device_table.setMinimumHeight(220)
        self.device_panel = QWidget()
        device_layout = QVBoxLayout(self.device_panel)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(10)
        self.device_count = QLabel("Local USB devices")
        device_layout.addWidget(self.device_count)
        device_layout.addWidget(self.device_table, 1)

        actions = QHBoxLayout()
        self.list_btn = self._make_button("List devices", "refresh")
        self.list_btn.clicked.connect(self.refresh_usbipd_devices)
        self.bind_btn = self._make_button("Bind / Share", "share")
        self.bind_btn.clicked.connect(self.bind_selected_device)
        self.unbind_btn = self._make_button("Unbind / Stop sharing", "disconnect")
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
        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.addWidget(QLabel("Activity log"))
        log_layout.addWidget(self.log_widget)
        self.log_widget.setMinimumHeight(100)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.device_panel)
        self.splitter.addWidget(log_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([480, 160])
        root.addWidget(self.splitter, 1)

        self.gate.changed.connect(self._update_controls)
        self._update_controls()
        QTimer.singleShot(0, self.refresh_usbipd_devices)

    _make_button = staticmethod(make_button)

    def log(self, message: str) -> None:
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
        idle = not self.is_busy and self.gate.available(self)
        self.list_btn.setEnabled(idle)
        self.device_combo.setEnabled(idle and bool(self.devices))
        self.bind_btn.setEnabled(idle and bool(self.devices))
        self.unbind_btn.setEnabled(idle and bool(self.devices))

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

    def _select_table_device(self) -> None:
        row = self.device_table.currentRow()
        if self.device_table.selectedItems() and 0 <= row < len(self.devices):
            self.device_combo.setCurrentIndex(row)

    def _select_combo_device(self, index: int) -> None:
        if 0 <= index < self.device_table.rowCount():
            self.device_table.selectRow(index)

    def _set_devices(self, devices: List[UsbipDevice], empty_text: str = "No USB devices detected") -> None:
        previous = self.device_combo.currentData()
        self.devices = devices
        self.device_combo.blockSignals(True)
        self.device_table.blockSignals(True)
        self.device_combo.clear()
        self.device_table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            self.device_combo.addItem(f"{device.busid} - {device.name}", device.busid)
            for column, value in enumerate((device.busid, device.vid_pid or "-",
                                            device.name or "Unknown device", device.state or "Not shared")):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.device_table.setItem(row, column, item)
        if devices:
            index = self.device_combo.findData(previous)
            index = max(0, index)
            self.device_combo.setCurrentIndex(index)
            self.device_table.selectRow(index)
        else:
            self.device_combo.addItem(empty_text)
        self.device_combo.blockSignals(False)
        self.device_table.blockSignals(False)
        self.device_combo.setEnabled(bool(devices))
        self.bind_btn.setEnabled(bool(devices))
        self.unbind_btn.setEnabled(bool(devices))
        self.device_count.setText(f"Local USB devices - {len(devices)} detected")

    def refresh_usbipd_devices(self):
        self.run_command("List USB devices", ["usbipd", "list"])

    def bind_selected_device(self) -> None:
        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Warning", "Select a device from the list.")
            return
        busid = self.devices[idx].busid
        self.run_command(f"Bind device {busid}", build_usbipd_bind_command(busid), refresh=True)

    def unbind_selected_device(self) -> None:
        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Warning", "Select a device from the list.")
            return
        busid = self.devices[idx].busid
        self.run_command(f"Unbind device {busid}", build_usbipd_unbind_command(busid), refresh=True)


class JoystickTab(QWidget):
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
        root.addWidget(panel)

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
        root.addWidget(QLabel("Joystick activity"))
        root.addWidget(self.log, 1)

        self.refresh_devices()

    def log_message(self, text: str) -> None:
        self._log_buffer.append(text)
        if len(self._log_buffer) > 200:
            self._log_buffer = self._log_buffer[-200:]
        self.log.setPlainText("\n".join(self._log_buffer))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def refresh_devices(self) -> None:
        if self._timer is not None:
            self._timer.stop()
        if self._current_joystick is not None:
            self._current_joystick.quit()
            self._current_joystick = None
        if pygame is None:
            self.device_combo.clear()
            self.device_combo.addItem("PyGame not installed")
            self.log_message("PyGame is not installed. Install it with: pip install pygame PyQt6")
            return

        pygame.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        self._devices = [f"Joystick {idx}" for idx in range(count)]

        self.device_combo.clear()
        if not self._devices:
            self.device_combo.addItem("No joysticks detected")
            self.log_message("No joysticks were detected on this machine.")
            return

        for device in self._devices:
            self.device_combo.addItem(device)
        self.log_message(f"Detected {count} joystick(s).")

    def connect_local_joystick(self) -> None:
        if pygame is None:
            QMessageBox.critical(self, "Error", "PyGame is not installed.")
            return

        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self._devices):
            QMessageBox.warning(self, "Warning", "Select a valid joystick.")
            return

        joystick = pygame.joystick.Joystick(idx)
        joystick.init()
        self._current_joystick = joystick

        self.log_message(f"Connected to {self._devices[idx]}.")

        if self._timer is not None:
            self._timer.stop()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.read_joystick_state)
        self._timer.start(20)

    def read_joystick_state(self) -> None:
        if self._current_joystick is None:
            return

        pygame.event.pump()
        joystick = self._current_joystick
        axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
        buttons = [bool(joystick.get_button(i)) for i in range(joystick.get_numbuttons())]
        hats = [joystick.get_hat(i) for i in range(joystick.get_numhats())]

        state = JoystickState(axes=axes, buttons=buttons, hats=hats)
        packet = JoystickPacket.from_state(state)
        self.log_message(f"Axes={axes} | Buttons={buttons} | Hats={hats} | Packet={packet}")


class UsbipJoystickBridgeApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._exit_requested = False
        self._shutdown_pending = False
        self._shutdown_ready = False
        self.setWindowTitle("USB/IP + Joystick Bridge")
        self.setWindowIcon(application_icon())
        self.resize(1100, 800)
        self.setStyleSheet(APP_STYLESHEET)
        self.setMinimumSize(900, 680)

        tabs = QTabWidget()
        self.operation_gate = OperationGate()
        self.host_tab = HostModeTab(self.operation_gate)
        tabs.addTab(self.host_tab, "Host Mode")
        self.client_tab = ClientModeTab(self.operation_gate)
        tabs.addTab(self.client_tab, "Client Mode")
        self.management_tab = ManagementTab(self.operation_gate)
        tabs.addTab(self.management_tab, "Management")
        self.joystick_tab = JoystickTab()
        tabs.addTab(self.joystick_tab, "Joystick")
        self.setCentralWidget(tabs)
        self.tray = SystemTray(self)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "tray"):
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
        if self._shutdown_ready:
            self.tray.icon.hide()
            event.accept()
            QApplication.instance().quit()
            return
        if self._shutdown_pending:
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
        if self.host_tab.is_busy:
            self.tray.restore()
            self.centralWidget().setCurrentWidget(self.host_tab)
            self.host_tab.log("Wait for the current host action to finish before closing.")
            event.ignore()
            return
        if self.client_tab.is_busy:
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
        if self.joystick_tab._timer is not None:
            self.joystick_tab._timer.stop()
        self.centralWidget().setEnabled(False)
        self.client_tab.disconnect_before_exit(self._finish_exit)

    def _finish_exit(self, success):
        self._shutdown_pending = False
        self.centralWidget().setEnabled(True)
        if success:
            self._shutdown_ready = True
            self.tray.icon.hide()
            self.hide()
            QApplication.instance().quit()
        else:
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
