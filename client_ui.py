"""Windows USB/IP client: remote exports and locally imported virtual ports."""

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                            QGroupBox, QLabel, QLineEdit, QSpinBox, QComboBox, QTextEdit)

from command_log import record_exception, record_result
from ui_theme import setup_page, make_button
from usbip_manager import (USBIP_TCP_PORT, build_usbip_list_command,
    build_usbip_attach_command, build_usbip_detach_command, parse_remote_devices,
    parse_imported_devices, resolve_usbip_client)


class ClientModeTab(QWidget):
    def __init__(self):
        super().__init__()
        self.devices = []
        self.imported_devices = []
        self._listed_endpoint = None
        self._process = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)
        root = QVBoxLayout(self)
        setup_page(root)
        help_text = QLabel("Connect this Windows PC to USB devices shared by another Windows PC.")
        help_text.setWordWrap(True)
        root.addWidget(help_text)

        remote = QGroupBox("Remote Windows host - usbipd-win")
        form = QFormLayout(remote)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("Host IP or name (LAN or Tailscale)")
        self.tcp_port_input = QSpinBox()
        self.tcp_port_input.setRange(1024, 65535)
        self.tcp_port_input.setValue(USBIP_TCP_PORT)
        self.tcp_port_input.setToolTip("usbipd-win listens on TCP 3240. Change only for an explicitly configured port forward.")
        form.addRow("Remote host", self.host_input)
        form.addRow("Server TCP port", self.tcp_port_input)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumContentsLength(24)
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        form.addRow("Exportable USB device", self.device_combo)
        actions = QHBoxLayout()
        self.list_btn = make_button("List remote devices", "refresh")
        self.list_btn.clicked.connect(self.refresh_remote_devices)
        self.attach_btn = make_button("Attach / Connect", "connect")
        self.attach_btn.setProperty("primary", True)
        self.attach_btn.clicked.connect(self.attach_selected_device)
        actions.addWidget(self.list_btn)
        actions.addWidget(self.attach_btn)
        actions.addStretch()
        form.addRow(actions)
        root.addWidget(remote)

        local = QGroupBox("Imported devices on this PC - usbip-win2")
        local_layout = QVBoxLayout(local)
        explanation = QLabel("Detach uses the device's virtual USB port, not the server TCP port.")
        explanation.setWordWrap(True)
        local_layout.addWidget(explanation)
        self.port_input = QComboBox()
        self.port_input.setMinimumContentsLength(24)
        self.port_input.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        local_layout.addWidget(self.port_input)
        local_actions = QHBoxLayout()
        self.refresh_imported_btn = make_button("Refresh connections", "refresh")
        self.refresh_imported_btn.clicked.connect(lambda: self.refresh_imported_devices())
        self.detach_btn = make_button("Detach / Disconnect", "disconnect")
        self.detach_btn.clicked.connect(self.detach_selected_device)
        local_actions.addWidget(self.refresh_imported_btn)
        local_actions.addWidget(self.detach_btn)
        local_actions.addStretch()
        local_layout.addLayout(local_actions)
        root.addWidget(local)
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.document().setMaximumBlockCount(300)
        self.log_widget.setPlaceholderText("Install usbip-win2 in Management on this PC, then list the remote host's devices.")
        root.addWidget(QLabel("Client activity"))
        root.addWidget(self.log_widget, 1)
        self.host_input.textChanged.connect(self._invalidate_remote)
        self.tcp_port_input.valueChanged.connect(self._invalidate_remote)
        self._invalidate_remote()
        self._set_imported([])

    @property
    def is_busy(self):
        return self._process is not None

    def log(self, message):
        cursor = self.log_widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(message + "\n")
        self.log_widget.setTextCursor(cursor)
        self.log_widget.ensureCursorVisible()

    def _endpoint(self):
        return self.host_input.text().strip(), self.tcp_port_input.value()

    def _invalidate_remote(self):
        self.devices = []
        self._listed_endpoint = None
        self.device_combo.clear()
        self.device_combo.addItem("List remote devices to select one")
        self._update_controls()

    def _update_controls(self):
        idle = not self.is_busy
        self.host_input.setEnabled(idle)
        self.tcp_port_input.setEnabled(idle)
        self.list_btn.setEnabled(idle and bool(self.host_input.text().strip()))
        self.device_combo.setEnabled(idle and bool(self.devices))
        self.attach_btn.setEnabled(idle and bool(self.devices) and self._listed_endpoint == self._endpoint())
        self.refresh_imported_btn.setEnabled(idle)
        self.port_input.setEnabled(idle and bool(self.imported_devices))
        self.detach_btn.setEnabled(idle and bool(self.imported_devices))

    def _set_imported(self, devices):
        previous = self.port_input.currentData()
        self.imported_devices = devices
        self.port_input.clear()
        for device in devices:
            self.port_input.addItem(f"Port {device.port} - {device.name} - {device.location}", device.port)
        if not devices:
            self.port_input.addItem("No imported devices detected")
        else:
            self.port_input.setCurrentIndex(max(0, self.port_input.findData(previous)))
        self._update_controls()

    def refresh_remote_devices(self):
        if self.is_busy:
            return
        host, tcp_port = self._endpoint()
        if not host:
            return
        previous = self.device_combo.currentData()
        self._invalidate_remote()
        def listed(output):
            self.devices = parse_remote_devices(output)
            self._listed_endpoint = (host, tcp_port)
            self.device_combo.clear()
            for device in self.devices:
                self.device_combo.addItem(f"{device.busid} - {device.name}", device.busid)
            if not self.devices:
                self.device_combo.addItem("No exportable devices on this host")
            else:
                self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(previous)))
            self.log(f"Detected {len(self.devices)} exportable USB device(s) on {host}:{tcp_port}.")
        self._run("List remote devices", build_usbip_list_command(host, tcp_port), listed)

    def refresh_imported_devices(self, after=None):
        if self.is_busy:
            return
        previous = self.port_input.currentData()
        self._set_imported([])
        def listed(output):
            self._set_imported(parse_imported_devices(output))
            self.port_input.setCurrentIndex(max(0, self.port_input.findData(previous)))
        self._run("List imported devices", ["usbip", "port"],
                  listed, after)

    def _refresh_after_action(self):
        self.refresh_imported_devices(after=self.refresh_remote_devices)

    def attach_selected_device(self):
        if self.is_busy or self._listed_endpoint != self._endpoint():
            return
        busid = self.device_combo.currentData()
        if busid is None:
            return
        host, port = self._endpoint()
        self._run(f"Attach {busid} from {host}", build_usbip_attach_command(host, busid, port),
                  after=self._refresh_after_action)

    def detach_selected_device(self):
        port = self.port_input.currentData()
        if self.is_busy or port is None:
            return
        self._run(f"Detach virtual port {port}", build_usbip_detach_command(str(port)),
                  after=self._refresh_after_action)

    def _run(self, label, command, callback=None, after=None):
        if self.is_busy:
            return
        try:
            command = [resolve_usbip_client(), *command[1:]]
        except FileNotFoundError as error:
            self.log(record_exception(label, command, error))
            self.log("Install usbip-win2 in Management on this Windows client.")
            self._update_controls()
            return
        self._label, self._command = label, command
        self._callback, self._after = callback, after
        self._timed_out = False
        process = QProcess(self)
        self._process = process
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        self.log(f"> {label}")
        self._update_controls()
        self._timer.start(30000)
        process.start(command[0], command[1:])

    def _timeout(self):
        if self._process:
            self._timed_out = True
            self._process.kill()

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self._process:
            self.log(record_exception(self._label, self._command, OSError(self._process.errorString())))
            self._cleanup()

    def _cleanup(self):
        self._timer.stop()
        self._process.deleteLater()
        self._process = None
        self._update_controls()

    def _finished(self, code, status):
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        error = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if self._timed_out or status == QProcess.ExitStatus.CrashExit:
            code = code or -1
        callback, after = self._callback, self._after
        self.log(record_result(self._label, self._command, code, output, error))
        if self._timed_out:
            self.log("The command timed out. Check the host address, USB/IP service and TCP 3240 firewall access.")
        self._cleanup()
        if code == 0 and callback:
            callback(output)
        self._update_controls()
        if after:
            after()
