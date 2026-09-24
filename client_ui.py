"""Windows USB/IP client: remote exports and locally imported virtual ports."""

from PyQt6.QtCore import Qt, pyqtSignal, QProcess, QTimer
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
                            QGroupBox, QLabel, QLineEdit, QSpinBox, QComboBox, QTextEdit, QScrollArea)

from device_presentation import ContentScrollArea, ActivityPanel, details_label
from ui_icons import line_icon, device_icon_kind

from operation_gate import OperationGate, defer_background_action
from command_log import record_exception, record_result
from ui_theme import setup_page, make_button
from usbip_manager import (USBIP_TCP_PORT, build_usbip_list_command,
    build_usbip_attach_command, build_usbip_detach_command, parse_remote_devices,
    parse_imported_devices, resolve_usbip_client, build_usbip_detach_all_command)


from client_devices import ClientDevices
from device_metadata import MetadataClient, merge_names


class ClientModeTab(ClientDevices, QWidget):
    activity = pyqtSignal(str)
    host_discovered = pyqtSignal(str)
    def __init__(self, gate=None, local_devices=None):
        super().__init__()
        self.gate = gate or OperationGate()
        self.metadata_client = MetadataClient(self)
        self.metadata_settings = None
        self.local_devices = local_devices or (lambda: [])
        self._remote_generation = 0
        self.devices = []
        self.imported_devices = []
        self._listed_endpoint = None
        self._process = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ContentScrollArea()
        scroll.setFrameShape(scroll.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        root = QVBoxLayout(content)
        setup_page(root)
        help_text = QLabel("Connect this Windows PC to USB devices shared by another Windows PC.")
        help_text.setWordWrap(True)
        root.addWidget(help_text)

        remote = QGroupBox("Remote Windows host")
        remote.setStyleSheet("QGroupBox { padding: 0px; }")
        form = QFormLayout(remote)
        form.setVerticalSpacing(8)
        form.setContentsMargins(12, 20, 12, 12)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("Host IP or name (LAN or Tailscale)")
        self.tcp_port_input = QSpinBox()
        self.tcp_port_input.setRange(1024, 65535)
        self.tcp_port_input.setValue(USBIP_TCP_PORT)
        self.tcp_port_input.setToolTip("usbipd-win listens on TCP 3240. Change only for an explicitly configured port forward.")
        host_row = QHBoxLayout()
        host_row.setSpacing(12)
        host_row.addWidget(self.host_input, 1)
        form.addRow("Remote host", host_row)
        form.addRow("Server TCP port", self.tcp_port_input)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumContentsLength(24)
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setParent(self)
        self.device_combo.hide()
        self.remote_details = details_label(compact=True)

        self.device_combo.currentIndexChanged.connect(self._show_remote_details)
        actions = QHBoxLayout()
        self.list_btn = make_button("List remote devices", "refresh")
        self.list_btn.clicked.connect(self.refresh_remote_devices)
        self.attach_btn = make_button("Connect", "connect")
        self.attach_btn.setProperty("primary", True)
        self.attach_btn.clicked.connect(self.attach_selected_device)
        host_row.addWidget(self.list_btn)
        actions.addWidget(self.attach_btn)
        actions.addStretch()
        action_panel = QWidget()
        action_panel.setLayout(actions)
        actions.setContentsMargins(0, 4, 0, 0)

        root.addWidget(remote)
        root.addWidget(self.setup_device_table())
        root.addWidget(QLabel("Connected devices - all hosts"))
        root.addWidget(self.connected_table)
        root.addWidget(self.remote_details)
        root.addWidget(action_panel)

        local = QGroupBox("Imported devices on this PC")
        local.setStyleSheet("QGroupBox { padding: 0px; }")
        local_layout = QVBoxLayout(local)
        local_layout.setContentsMargins(12, 20, 12, 12)
        local_layout.setSpacing(8)
        explanation = QLabel("Detach uses the device's virtual USB port, not the server TCP port.")
        explanation.setWordWrap(True)
        local_layout.addWidget(explanation)
        self.port_input = QComboBox()
        self.port_input.setMinimumContentsLength(24)
        self.port_input.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        local_layout.addWidget(self.port_input)
        self.imported_details = details_label(compact=True)
        local_layout.addWidget(self.imported_details)
        self.port_input.currentIndexChanged.connect(self._show_imported_details)
        local_actions = QHBoxLayout()
        self.refresh_imported_btn = make_button("Refresh connections", "refresh")
        self.refresh_imported_btn.clicked.connect(lambda: self.refresh_imported_devices())
        self.detach_btn = make_button("Disconnect", "disconnect")
        self.detach_btn.clicked.connect(self.detach_selected_device)
        self.detach_all_btn = make_button("Disconnect all", "disconnect")
        self.detach_all_btn.setToolTip("Disconnect all USB/IP devices imported into this PC, from every host.")
        self.detach_all_btn.clicked.connect(self.detach_all_devices)
        local_actions.addWidget(self.refresh_imported_btn)
        local_actions.addWidget(self.detach_btn)
        local_actions.addWidget(self.detach_all_btn)
        local_actions.addStretch()
        local_layout.addLayout(local_actions)
        local.setParent(self)
        local.hide()
        actions.insertWidget(0, self.refresh_imported_btn)
        actions.insertWidget(2, self.detach_btn)
        actions.insertWidget(3, self.detach_all_btn)
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.document().setMaximumBlockCount(300)
        self.log_widget.setPlaceholderText("Install usbip-win2 in Components on this PC, then list the remote host's devices.")
        self.activity_panel = ActivityPanel(self.log_widget)
        root.addWidget(self.activity_panel)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.host_input.textChanged.connect(self._invalidate_remote)
        self.tcp_port_input.valueChanged.connect(self._invalidate_remote)
        self._invalidate_remote()
        self._set_imported([])
        self.gate.changed.connect(self._update_controls)

    def prefer_local_device_names(self, host, port, devices):
        """Use Windows names only for a verified local standard-service endpoint."""
        from ipaddress import ip_address
        from dataclasses import replace
        try:
            local = ip_address(host.strip().strip("[]")).is_loopback
        except ValueError:
            local = host.strip().casefold().rstrip(".") == "localhost"
        if not local or port != USBIP_TCP_PORT:
            return devices
        known = {device.busid: device for device in self.local_devices()}
        result = []
        for device in devices:
            candidate = known.get(device.busid)
            if (candidate and candidate.name and device.vid_pid and
                    candidate.vid_pid.casefold() == device.vid_pid.casefold()):
                device = replace(device, name=candidate.name)
            result.append(device)
        return result

    def _show_remote_details(self):
        busid = self.device_combo.currentData()
        device = next((d for d in self.devices if d.busid == busid), None)
        if device:
            host, port = self._endpoint()
            self.remote_details.setText(f"{device.name}\nExported by {host}:{port} - connection availability is checked when connecting.\n"
                f"BUSID: {device.busid} | VID:PID: {device.vid_pid or '-'}")
        else:
            self.remote_details.setText("List remote devices and select one to see its details.")

    def _show_imported_details(self):
        port = self.port_input.currentData()
        device = next((d for d in self.imported_devices if d.port == port), None)
        self.imported_details.setText(f"{device.name}\nImported on this PC | Virtual USB port: {device.port}\n"
            f"Source: {device.location}" if device else "No imported device selected.")

    @property
    def is_busy(self):
        return self._process is not None

    def log(self, message):
        if getattr(self, "_silent_logs", None) is not None:
            self._silent_logs.append(message)
            return
        self.activity_panel.update_message(message)
        self.activity.emit(message)
        cursor = self.log_widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(message + "\n")
        self.log_widget.setTextCursor(cursor)
        self.log_widget.ensureCursorVisible()

    def _endpoint(self):
        return self.host_input.text().strip(), self.tcp_port_input.value()

    def cancel_metadata(self):
        self.metadata_client.cancel()

    def _invalidate_remote(self):
        self._remote_generation += 1
        self.cancel_metadata()
        self.devices = []
        self._listed_endpoint = None
        self.device_combo.clear()
        self.device_combo.addItem("List remote devices to select one")
        self.rebuild_device_table()
        self._update_controls()

    def _update_controls(self):
        if self.gate.background:
            return
        idle = not self.is_busy and self.gate.available(self)
        self.host_input.setEnabled(idle)
        self.tcp_port_input.setEnabled(idle)
        self.list_btn.setEnabled(idle and bool(self.host_input.text().strip()))
        self.device_combo.setEnabled(idle and bool(self.devices))
        self.attach_btn.setEnabled(idle and self.device_combo.currentData() is not None and self.port_input.currentData() is None and self._listed_endpoint == self._endpoint())
        self.refresh_imported_btn.setEnabled(idle)
        self.port_input.setEnabled(idle and bool(self.imported_devices))
        self.detach_btn.setEnabled(idle and self.port_input.currentData() is not None)
        self.detach_all_btn.setEnabled(idle and bool(self.imported_devices))

    def _set_imported(self, devices):
        if self.gate.background and self.imported_devices == devices:
            return
        previous = self.port_input.currentData()
        self.imported_devices = devices
        self.port_input.clear()
        for device in devices:
            self.port_input.addItem(line_icon(device_icon_kind(device.name)), f"{device.name} - Port {device.port}", device.port)
        if not devices:
            self.port_input.addItem("No imported devices detected")
        else:
            self.port_input.setCurrentIndex(max(0, self.port_input.findData(previous)))
        self.rebuild_device_table()
        self._update_controls()

    @defer_background_action
    def refresh_remote_devices(self):
        if self.is_busy:
            return
        host, tcp_port = self._endpoint()
        if not host:
            return
        manual = not self.gate.background
        previous = self.device_combo.currentData()
        self.cancel_metadata()
        self._remote_generation += 1
        generation = self._remote_generation
        def failed():
            if generation == self._remote_generation and (host, tcp_port) == self._endpoint():
                self._invalidate_remote()
        def listed(output):
            if generation != self._remote_generation or (host, tcp_port) != self._endpoint():
                return
            devices = self.prefer_local_device_names(host, tcp_port, parse_remote_devices(output))
            if devices == self.devices and self._listed_endpoint == (host, tcp_port):
                if manual:
                    self.log(f"Detected {len(devices)} exportable USB device(s) on {host}:{tcp_port}.")
                    if devices:
                        self.host_discovered.emit(host)
                self.retrieve_metadata(host, tcp_port)
                return
            self.devices = devices
            self._listed_endpoint = (host, tcp_port)
            self.device_combo.blockSignals(True)
            self.device_combo.clear()
            for device in self.devices:
                self.device_combo.addItem(line_icon(device_icon_kind(device.name)), f"{device.busid} - {device.name}", device.busid)
            if not self.devices:
                self.device_combo.addItem("No exportable devices on this host")
            else:
                self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(previous)))
            self.device_combo.blockSignals(False)
            self.rebuild_device_table()
            self.log(f"Detected {len(self.devices)} exportable USB device(s) on {host}:{tcp_port}.")
            self.retrieve_metadata(host, tcp_port)
            if manual and devices:
                self.host_discovered.emit(host)
        self._run("List remote devices", build_usbip_list_command(host, tcp_port), listed,
                  on_failure=failed)

    def retrieve_metadata(self, host, tcp_port):
        settings = self.metadata_settings
        if settings is None or str(settings.value("metadata/retrieve", "false")).lower() != "true":
            return
        try:
            port = int(settings.value("metadata/port", 3241))
        except (ValueError, TypeError):
            return
        if not 1024 <= port <= 65535 or port == tcp_port:
            return
        snapshot = list(self.devices)
        def received(payload):
            if self._endpoint() != (host, tcp_port) or self.devices != snapshot or self.gate.shutting_down:
                return
            updated = merge_names(snapshot, payload)
            if updated == self.devices:
                return
            self.devices = updated
            for i, device in enumerate(updated):
                self.device_combo.setItemText(i, f"{device.busid} - {device.name}")
                self.device_combo.setItemIcon(i, line_icon(device_icon_kind(device.name)))
            self.rebuild_device_table()
        self.metadata_client.fetch(host, port, received)

    @defer_background_action
    def refresh_imported_devices(self, after=None):
        if self.is_busy:
            return
        previous = self.port_input.currentData()
        def listed(output):
            self._set_imported(parse_imported_devices(output))
        self._run("List imported devices", ["usbip", "port"],
                  listed, after)

    def _refresh_after_action(self):
        self.refresh_imported_devices(after=self.refresh_remote_devices)

    @defer_background_action
    def attach_selected_device(self):
        if self.is_busy or self._listed_endpoint != self._endpoint():
            return
        busid = self.device_combo.currentData()
        if busid is None:
            return
        host, port = self._endpoint()
        self._run(f"Attach {busid} from {host}", build_usbip_attach_command(host, busid, port),
                  after=self._refresh_after_action)

    @defer_background_action
    def detach_selected_device(self):
        port = self.port_input.currentData()
        if self.is_busy or port is None:
            return
        self._run(f"Detach virtual port {port}", build_usbip_detach_command(str(port)),
                  after=self._refresh_after_action)

    @defer_background_action
    def detach_all_devices(self):
        if self.is_busy or not self.imported_devices:
            return
        self._run("Detach all imported USB devices", build_usbip_detach_all_command(),
                  after=self._refresh_after_action)

    def disconnect_before_exit(self, done):
        """Query fresh state, detach all imports and verify before allowing exit."""
        from usbip_installer import find_client_installation
        if self.is_busy or not self.gate.available(self):
            done(False)
            return
        try:
            resolve_usbip_client()
        except FileNotFoundError:
            # Host-only installations have no client devices to clean up.
            try:
                done(not self.imported_devices and find_client_installation() is None)
            except OSError as error:
                self.log(record_exception("Check client installation", ["usbip"], error))
                done(False)
            return
        except OSError as error:
            self.log(record_exception("Check client installation", ["usbip"], error))
            done(False)
            return
        def failed():
            done(False)
        def verified(output):
            devices = parse_imported_devices(output)
            self._set_imported(devices)
            done(not devices)
        def detached(output):
            self._run("Verify devices are disconnected", ["usbip", "port"], verified, on_failure=failed)
        def listed(output):
            devices = parse_imported_devices(output)
            self._set_imported(devices)
            if not devices:
                done(True)
            else:
                self._run("Disconnect all devices before exit", build_usbip_detach_all_command(),
                          detached, on_failure=failed)
        self._run("Check connections before exit", ["usbip", "port"], listed, on_failure=failed)

    def _run(self, label, command, callback=None, after=None, on_failure=None):
        if self.is_busy:
            if on_failure:
                on_failure()
            return
        try:
            command = [resolve_usbip_client(), *command[1:]]
        except OSError as error:
            self.log(record_exception(label, command, error))
            self.log("Install usbip-win2 in Components on this Windows client.")
            self._update_controls()
            if on_failure:
                on_failure()
            return
        if not self.gate.acquire(self):
            self.log("Wait for the current USB/IP or management action to finish.")
            if on_failure:
                on_failure()
            return
        self._label, self._command = label, command
        self._callback, self._after = callback, after
        self._on_failure = on_failure
        self._timed_out = False
        self._background_cancelled = False
        process = QProcess(self)
        self._process = process
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._error)
        self.log(f"> {label}")
        self._update_controls()
        self._timer.start(5000 if self.gate.background and label == "List remote devices" else 30000)
        process.start(command[0], command[1:])

    def cancel_background_query(self):
        """Yield a read-only poll to user actions without clearing known devices."""
        if (self.gate.background and self._process is not None
                and self._label in {"List remote devices", "List imported devices"}):
            self._background_cancelled = True
            self._timer.stop()
            self._process.kill()

    def _timeout(self):
        if self._process:
            self._timed_out = True
            self._process.kill()

    def _error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self._process:
            self.log(record_exception(self._label, self._command, OSError(self._process.errorString())))
            failed = self._on_failure
            self._cleanup()
            if failed:
                failed()

    def _cleanup(self):
        self._timer.stop()
        self._process.deleteLater()
        self._process = None
        self.gate.release(self)
        self._update_controls()

    def _finished(self, code, status):
        if self._process is None:
            return
        if self._background_cancelled:
            self._cleanup()
            return
        output = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        error = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if self._timed_out or status == QProcess.ExitStatus.CrashExit:
            code = code or -1
        callback, after, failed = self._callback, self._after, self._on_failure
        self.log(record_result(self._label, self._command, code, output, error))
        if code != 0 and self._label == "List imported devices":
            self._set_imported([])
        if code != 0 and self._label == "List remote devices":
            host = self._command[-1]
            port = next((part.split("=", 1)[1] for part in self._command if part.startswith("--tcp-port=")), "3240")
            self.log(f"Unable to list devices from {host}:{port}. Check the host name or IP address. "
                     "For this computer, enter 127.0.0.1. For another computer, enter its IP address or DNS name. "
                     "Also check that its USB/IP service is running and reachable.")
            if host.lower() == "locahost":
                self.log("Did you mean localhost? The entered name is locahost (missing the second l).")
        if self._timed_out:
            self.log("The command timed out. Check the host address, USB/IP service and TCP 3240 firewall access.")
        self._cleanup()
        if code == 0 and callback:
            callback(output)
        elif code != 0 and failed:
            failed()
        self._update_controls()
        if after:
            after()
