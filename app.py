import os
import shutil
import subprocess
import sys
from typing import List, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QMainWindow,
    QMessageBox,
    QPushButton,
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

from joystick_bridge import JoystickPacket, JoystickState
from usbip_manager import (
    UsbipDevice,
    build_usbip_attach_command,
    build_usbip_detach_command,
    build_usbip_win2_install_command,
    build_usbipd_bind_command,
    build_usbipd_install_command,
    build_usbipd_unbind_command,
    parse_usbipd_list,
)


class UsbipTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.devices: List[UsbipDevice] = []
        self._log_buffer: List[str] = []

        root = QVBoxLayout(self)

        host_mode_group = QGroupBox("Host mode")
        host_layout = QVBoxLayout(host_mode_group)

        self.host_input = QComboBox()
        self.host_input.setEditable(True)
        self.host_input.addItem("192.168.1.10")
        self.host_input.addItem("10.0.0.5")
        self.host_input.addItem("localhost")
        host_layout.addWidget(self.host_input)

        self.device_combo = QComboBox()
        self.device_combo.addItem("No shared USB devices")
        host_layout.addWidget(self.device_combo)

        self.device_table = QTableWidget(0, 4)
        self.device_table.setHorizontalHeaderLabels(["BUSID", "VID:PID", "DEVICE", "STATE"])
        self.device_table.verticalHeader().setVisible(False)
        self.device_table.setAlternatingRowColors(True)
        self.device_table.setSelectionBehavior(self.device_table.SelectionBehavior.SelectRows)
        self.device_table.setSelectionMode(self.device_table.SelectionMode.SingleSelection)
        self.device_table.setEditTriggers(self.device_table.EditTrigger.NoEditTriggers)
        self.device_table.horizontalHeader().setStretchLastSection(True)
        self.device_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.device_table.setMinimumHeight(220)
        host_layout.addWidget(self.device_table)

        host_actions = QHBoxLayout()
        self.list_btn = self._make_button("📋 List devices")
        self.list_btn.clicked.connect(self.refresh_usbipd_devices)
        self.bind_btn = self._make_button("🔒 Bind / share")
        self.bind_btn.clicked.connect(self.bind_selected_device)
        self.unbind_btn = self._make_button("🔓 Unbind / stop sharing")
        self.unbind_btn.clicked.connect(self.unbind_selected_device)
        host_actions.addWidget(self.list_btn)
        host_actions.addWidget(self.bind_btn)
        host_actions.addWidget(self.unbind_btn)
        host_layout.addLayout(host_actions)

        client_mode_group = QGroupBox("Client mode")
        client_layout = QVBoxLayout(client_mode_group)
        self.port_input = QComboBox()
        self.port_input.setEditable(True)
        self.port_input.addItem("1")
        self.port_input.addItem("2")
        self.port_input.addItem("3")
        client_layout.addWidget(self.port_input)

        client_actions = QHBoxLayout()
        self.attach_btn = self._make_button("🔌 Attach / connect")
        self.attach_btn.clicked.connect(self.attach_selected_device)
        self.detach_btn = self._make_button("🧯 Detach / disconnect")
        self.detach_btn.clicked.connect(self.detach_selected_device)
        client_actions.addWidget(self.attach_btn)
        client_actions.addWidget(self.detach_btn)
        client_layout.addLayout(client_actions)

        management_group = QGroupBox("Management / Administration")
        management_layout = QVBoxLayout(management_group)

        self.usbipd_installed_check = QCheckBox("usbipd-win installed")
        self.usbipd_installed_check.setEnabled(False)
        self.usbip_win2_installed_check = QCheckBox("usbip-win2 installed")
        self.usbip_win2_installed_check.setEnabled(False)

        management_buttons = QHBoxLayout()
        self.install_usbipd_btn = self._make_button("⬇ Install usbipd-win")
        self.install_usbipd_btn.clicked.connect(self.install_usbipd)

        self.uninstall_usbipd_btn = self._make_button("🗑 Uninstall usbipd-win")
        self.uninstall_usbipd_btn.clicked.connect(self.uninstall_usbipd)

        self.install_usbip_win2_btn = self._make_button("🔧 Install usbip-win2")
        self.install_usbip_win2_btn.clicked.connect(self.install_usbip_win2)

        self.uninstall_usbip_win2_btn = self._make_button("🧹 Open usbip-win2 uninstall")
        self.uninstall_usbip_win2_btn.clicked.connect(self.uninstall_usbip_win2)

        management_buttons.addWidget(self.install_usbipd_btn)
        management_buttons.addWidget(self.uninstall_usbipd_btn)
        management_buttons.addWidget(self.install_usbip_win2_btn)
        management_buttons.addWidget(self.uninstall_usbip_win2_btn)

        management_layout.addWidget(self.usbipd_installed_check)
        management_layout.addWidget(self.usbip_win2_installed_check)
        management_layout.addLayout(management_buttons)

        root.addWidget(host_mode_group)
        root.addWidget(client_mode_group)
        root.addWidget(management_group)

        actions = QHBoxLayout()
        self.list_btn = self._make_button("📋 List devices")
        self.list_btn.clicked.connect(self.refresh_usbipd_devices)

        self.bind_btn = self._make_button("🔒 Bind / share")
        self.bind_btn.clicked.connect(self.bind_selected_device)

        self.unbind_btn = self._make_button("🔓 Unbind / stop sharing")
        self.unbind_btn.clicked.connect(self.unbind_selected_device)

        self.attach_btn = self._make_button("🔌 Attach / connect")
        self.attach_btn.clicked.connect(self.attach_selected_device)

        self.detach_btn = self._make_button("🧯 Detach / disconnect")
        self.detach_btn.clicked.connect(self.detach_selected_device)

        for button in [
            self.list_btn,
            self.bind_btn,
            self.unbind_btn,
            self.attach_btn,
            self.detach_btn,
        ]:
            actions.addWidget(button)

        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setPlaceholderText("USB/IP process logs...")

        root.addLayout(actions)
        root.addWidget(self.log_widget)

        self.refresh_installation_status()
        self.refresh_usbipd_devices()

    @staticmethod
    def _make_button(text: str) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(
            "QPushButton {"
            "  min-height: 40px;"
            "  border-radius: 10px;"
            "  padding: 8px 14px;"
            "  font-weight: 600;"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e0ecff, stop:1 #dfe7ff);"
            "  color: #112240;"
            "  border: 1px solid #bfd0ff;"
            "}"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f6fed, stop:1 #4b8bf4); color: white; }"
        )
        return button

    def log(self, message: str) -> None:
        self._log_buffer.append(message)
        if len(self._log_buffer) > 250:
            self._log_buffer = self._log_buffer[-250:]
        self.log_widget.setPlainText("\n".join(self._log_buffer))
        self.log_widget.verticalScrollBar().setValue(self.log_widget.verticalScrollBar().maximum())

    def run_command(self, label: str, command: List[str]) -> None:
        try:
            self.log(f"> {label}")
            self.log(f"Running: {' '.join(command)}")
            result = subprocess.run(command, capture_output=True, text=True, shell=False, check=False)

            if result.stdout:
                self.log(result.stdout.strip())
            if result.stderr:
                self.log(result.stderr.strip())

            if result.returncode == 0:
                self.log(f"[OK] {label}")
            else:
                self.log(f"[ERROR] {label} (exit code: {result.returncode})")

        except FileNotFoundError as exc:
            self.log(f"[ERROR] Executable not found: {exc}")
        except Exception as exc:  # pragma: no cover
            self.log(f"[ERROR] Exception: {exc}")

    def refresh_usbipd_devices(self) -> None:
        self.run_command("List usbipd devices", ["usbipd", "list"])
        self._refresh_after_list()

    def _refresh_after_list(self) -> None:
        try:
            result = subprocess.run(["usbipd", "list"], capture_output=True, text=True, shell=False, check=False)
            if result.returncode != 0:
                self.device_combo.clear()
                self.device_combo.addItem("Unable to list devices")
                self.log("usbipd is not installed or not available in PATH.")
                return

            devices = parse_usbipd_list(result.stdout)
            self.devices = devices
            self.device_combo.clear()

            if not devices:
                self.device_combo.clear()
                self.device_combo.addItem("No shared USB devices")
                self.device_table.setRowCount(0)
                self.log("No USB devices are shared yet or no bind has been performed.")
                return

            self.device_combo.clear()
            self.device_table.setRowCount(len(devices))
            for row_index, device in enumerate(devices):
                vid_pid = device.vid_pid or "-"
                state = device.state or "Not shared"
                name = device.name or "Unknown device"
                self.device_combo.addItem(f"{device.busid} - {name}")

                self.device_table.setItem(row_index, 0, QTableWidgetItem(device.busid))
                self.device_table.setItem(row_index, 1, QTableWidgetItem(vid_pid))
                self.device_table.setItem(row_index, 2, QTableWidgetItem(name))
                self.device_table.setItem(row_index, 3, QTableWidgetItem(state))

            self.device_table.resizeColumnsToContents()
            self.log(f"Detected {len(devices)} USB device(s).")
        except Exception as exc:  # pragma: no cover
            self.log(f"[ERROR] USB/IP device listing: {exc}")

    def _is_usbipd_installed(self) -> bool:
        return shutil.which("usbipd") is not None

    def _is_usbip_win2_installed(self) -> bool:
        candidate_dirs = [
            os.path.join(os.environ.get("ProgramFiles", "C:/Program Files"), "usbip-win2"),
            os.path.join(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"), "usbip-win2"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "usbip-win2"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "usbipd-win"),
        ]
        return any(os.path.isdir(path) for path in candidate_dirs if path)

    def refresh_installation_status(self) -> None:
        self.usbipd_installed_check.setChecked(self._is_usbipd_installed())
        self.usbip_win2_installed_check.setChecked(self._is_usbip_win2_installed())

    def install_usbipd(self) -> None:
        self.run_command("Install usbipd-win", build_usbipd_install_command())
        self.refresh_installation_status()

    def uninstall_usbipd(self) -> None:
        if not self._is_usbipd_installed():
            QMessageBox.information(self, "usbipd-win", "usbipd-win is not currently installed.")
            return
        self.run_command("Uninstall usbipd-win", ["winget", "uninstall", "usbipd"])
        self.refresh_installation_status()

    def install_usbip_win2(self) -> None:
        self.run_command("Open usbip-win2 download", build_usbip_win2_install_command())
        self.refresh_installation_status()

    def uninstall_usbip_win2(self) -> None:
        self.run_command(
            "Open usbip-win2 uninstall guidance",
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "Start-Process https://github.com/vadimgrn/usbip-win2/releases/latest -Verb Open",
            ],
        )
        self.refresh_installation_status()

    def bind_selected_device(self) -> None:
        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Warning", "Select a device from the list.")
            return
        busid = self.devices[idx].busid
        self.run_command(f"Bind device {busid}", build_usbipd_bind_command(busid))

    def unbind_selected_device(self) -> None:
        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Warning", "Select a device from the list.")
            return
        busid = self.devices[idx].busid
        self.run_command(f"Unbind device {busid}", build_usbipd_unbind_command(busid))

    def attach_selected_device(self) -> None:
        host = self.host_input.currentText().strip()
        if not host:
            QMessageBox.warning(self, "Warning", "Enter a valid IP or host for the remote machine.")
            return
        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Warning", "Select a shared device before connecting.")
            return
        busid = self.devices[idx].busid
        self.run_command(f"Attach device {busid} from {host}", build_usbip_attach_command(host, busid))

    def detach_selected_device(self) -> None:
        port = self.port_input.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Warning", "Enter a valid USB/IP port number to detach.")
            return
        self.run_command(f"Detach port {port}", build_usbip_detach_command(port))


class JoystickTab(QWidget):
    @staticmethod
    def _make_button(text: str) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(
            "QPushButton {"
            "  min-height: 40px;"
            "  border-radius: 10px;"
            "  padding: 8px 14px;"
            "  font-weight: 600;"
            "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #e0ecff, stop:1 #dfe7ff);"
            "  color: #112240;"
            "  border: 1px solid #bfd0ff;"
            "}"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2f6fed, stop:1 #4b8bf4); color: white; }"
        )
        return button

    def __init__(self) -> None:
        super().__init__()
        self._devices: List[str] = []
        self._current_joystick: Optional[object] = None
        self._timer: Optional[QTimer] = None
        self._log_buffer: List[str] = []

        root = QVBoxLayout(self)

        panel = QGroupBox("Joystick connection")
        form = QFormLayout(panel)
        self.device_combo = QComboBox()
        self.device_combo.addItem("No joysticks detected")
        form.addRow("Local joystick:", self.device_combo)
        root.addWidget(panel)

        self.connect_btn = self._make_button("🎮 Connect")
        self.connect_btn.clicked.connect(self.connect_local_joystick)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Joystick logs...")

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.connect_btn)
        buttons_row.addStretch(1)
        root.addLayout(buttons_row)
        root.addWidget(self.log)

        self.refresh_devices()

    def log_message(self, text: str) -> None:
        self._log_buffer.append(text)
        if len(self._log_buffer) > 200:
            self._log_buffer = self._log_buffer[-200:]
        self.log.setPlainText("\n".join(self._log_buffer))
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def refresh_devices(self) -> None:
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

        joystick = self._current_joystick
        axes = [joystick.get_axis(i) for i in range(joystick.get_numaxes())]
        buttons = [bool(joystick.get_button(i)) for i in range(joystick.get_numbuttons())]
        hats = [joystick.get_hat(0)] if joystick.get_numhats() > 0 else []

        state = JoystickState(axes=axes, buttons=buttons, hats=hats)
        packet = JoystickPacket.from_state(state)
        self.log_message(f"Axes={axes} | Buttons={buttons} | Hats={hats} | Packet={packet}")


class UsbipJoystickBridgeApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("USB/IP + Joystick Bridge")
        self.resize(1100, 800)
        self.setStyleSheet(
            "QMainWindow { background: #0b1220; color: #e2e8f0; }"
            "QWidget { background: #0b1220; color: #e2e8f0; }"
            "QTabWidget::pane { border: 1px solid #1f2937; border-radius: 12px; background: #111827; }"
            "QTabBar::tab { background: #1f2937; color: #cbd5e1; padding: 10px 18px; border: 1px solid #334155; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 4px; }"
            "QTabBar::tab:selected { background: #111827; color: #f8fafc; border: 1px solid #38bdf8; }"
            "QGroupBox { border: 1px solid #334155; border-radius: 10px; margin-top: 12px; padding-top: 10px; background: #111827; color: #e2e8f0; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #7dd3fc; }"
            "QComboBox, QTextEdit, QLineEdit { background: #0f172a; color: #e2e8f0; border: 1px solid #475569; border-radius: 8px; padding: 6px 8px; }"
            "QComboBox::drop-down { border: none; background: transparent; }"
            "QTextEdit { background: #0f172a; }"
            "QPushButton { min-height: 40px; border-radius: 10px; padding: 8px 14px; font-weight: 600; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #1d4ed8); color: white; border: 1px solid #60a5fa; }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b82f6, stop:1 #2563eb); }"
            "QPushButton:pressed { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1e40af, stop:1 #1d4ed8); }"
            "QLabel { color: #e2e8f0; }"
            "QScrollBar:vertical { background: #0b1220; width: 10px; }"
            "QScrollBar::handle:vertical { background: #475569; border-radius: 5px; }"
        )

        tabs = QTabWidget()
        tabs.addTab(UsbipTab(), "USB/IP")
        tabs.addTab(JoystickTab(), "Joystick")
        self.setCentralWidget(tabs)


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = UsbipJoystickBridgeApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
