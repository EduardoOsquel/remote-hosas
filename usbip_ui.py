import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from usbip_manager import (
    UsbipDevice,
    build_usbip_attach_command,
    build_usbip_win2_install_command,
    build_usbipd_bind_command,
    build_usbipd_install_command,
    parse_usbipd_list,
)


@dataclass
class UsbipTask:
    label: str
    command: List[str]
    working_dir: Optional[str] = None


class UsbipControllerApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("USB/IP Bridge Manager")
        self.resize(1100, 780)

        self.devices: List[UsbipDevice] = []
        self.host_input = None
        self.device_combo = None
        self.log_widget = None
        self._log_buffer: List[str] = []
        self._refresh_timer: Optional[QTimer] = None

        self.init_ui()
        self.refresh_usbipd_devices()

    def init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QGroupBox("Configuración")
        form = QFormLayout(top)

        self.host_input = QComboBox()
        self.host_input.setEditable(True)
        self.host_input.addItem("192.168.1.10")
        self.host_input.addItem("10.0.0.5")
        self.host_input.addItem("localhost")
        form.addRow("Host remoto / WSL:", self.host_input)

        self.device_combo = QComboBox()
        self.device_combo.addItem("No hay dispositivos compartidos")
        form.addRow("Dispositivo USB:", self.device_combo)

        actions = QHBoxLayout()

        self.list_btn = QPushButton("Listar dispositivos")
        self.list_btn.clicked.connect(self.refresh_usbipd_devices)

        self.install_usbipd_btn = QPushButton("Instalar usbipd-win")
        self.install_usbipd_btn.clicked.connect(self.install_usbipd)

        self.install_usbip_win2_btn = QPushButton("Descargar usbip-win2")
        self.install_usbip_win2_btn.clicked.connect(self.install_usbip_win2)

        self.bind_btn = QPushButton("Bind / compartir")
        self.bind_btn.clicked.connect(self.bind_selected_device)

        self.attach_btn = QPushButton("Attach / conectar")
        self.attach_btn.clicked.connect(self.attach_selected_device)

        for button in [
            self.list_btn,
            self.install_usbipd_btn,
            self.install_usbip_win2_btn,
            self.bind_btn,
            self.attach_btn,
        ]:
            actions.addWidget(button)

        root.addWidget(top)
        root.addLayout(actions)

        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setPlaceholderText("Logs del proceso USB/IP...")
        root.addWidget(self.log_widget)

        self.statusBar().showMessage("Listo")

    def log(self, message: str) -> None:
        self._log_buffer.append(message)
        if len(self._log_buffer) > 250:
            self._log_buffer = self._log_buffer[-250:]
        self.log_widget.setPlainText("\n".join(self._log_buffer))
        self.log_widget.verticalScrollBar().setValue(self.log_widget.verticalScrollBar().maximum())

    def run_command(self, task: UsbipTask, callback=None) -> None:
        def worker() -> None:
            try:
                self.log(f"> {task.label}")
                self.log(f"Ejecutando: {' '.join(task.command)}")
                result = subprocess.run(
                    task.command,
                    capture_output=True,
                    text=True,
                    shell=False,
                    cwd=task.working_dir,
                    check=False,
                )

                if result.stdout:
                    self.log(result.stdout.strip())
                if result.stderr:
                    self.log(result.stderr.strip())

                if result.returncode == 0:
                    self.log(f"[OK] {task.label}")
                else:
                    self.log(f"[ERROR] {task.label} (código: {result.returncode})")

                if callback is not None:
                    callback(result)

            except FileNotFoundError as exc:
                self.log(f"[ERROR] No se encontró el ejecutable: {exc}")
            except Exception as exc:  # pragma: no cover
                self.log(f"[ERROR] Excepción: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def refresh_usbipd_devices(self) -> None:
        self.run_command(
            UsbipTask(
                label="Listar dispositivos usbipd",
                command=["usbipd", "list"],
            ),
            callback=self._on_list_done,
        )

    def _on_list_done(self, result) -> None:
        if result.returncode != 0:
            self.device_combo.clear()
            self.device_combo.addItem("No se pudo listar dispositivos")
            self.log("usbipd no está instalado o no está disponible en PATH.")
            return

        output = result.stdout.strip()
        devices = parse_usbipd_list(output)
        self.devices = devices
        self.device_combo.clear()

        if not devices:
            self.device_combo.addItem("No hay dispositivos compartidos")
            self.log("No hay dispositivos USB compartidos o aún no se ha hecho bind.")
            return

        for dev in devices:
            self.device_combo.addItem(f"{dev.busid} - {dev.name}")
        self.log(f"Se detectaron {len(devices)} dispositivos USB compartidos.")

    def install_usbipd(self) -> None:
        self.run_command(UsbipTask(label="Instalar usbipd-win", command=build_usbipd_install_command()))

    def install_usbip_win2(self) -> None:
        self.run_command(UsbipTask(label="Abrir descarga de usbip-win2", command=build_usbip_win2_install_command()))

    def bind_selected_device(self) -> None:
        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Advertencia", "Selecciona un dispositivo de la lista.")
            return

        busid = self.devices[idx].busid
        self.run_command(
            UsbipTask(label=f"Hacer bind del dispositivo {busid}", command=build_usbipd_bind_command(busid))
        )

    def attach_selected_device(self) -> None:
        host = self.host_input.currentText().strip() or self.host_input.lineEdit().text().strip()
        if not host:
            QMessageBox.warning(self, "Advertencia", "Introduce una IP o host válido para el equipo remoto.")
            return

        idx = self.device_combo.currentIndex()
        if idx < 0 or idx >= len(self.devices):
            QMessageBox.warning(self, "Advertencia", "Selecciona un dispositivo compartido antes de conectar.")
            return

        busid = self.devices[idx].busid
        self.run_command(
            UsbipTask(
                label=f"Conectar dispositivo {busid} desde {host}",
                command=build_usbip_attach_command(host, busid),
            )
        )


def main() -> None:
    app = QApplication(sys.argv)
    window = UsbipControllerApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
