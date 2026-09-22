"""Dependency management UI; external commands run without blocking Qt."""

import os
import json
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QProcess
from PyQt6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QTextEdit,
    QVBoxLayout, QWidget,
)

from operation_gate import OperationGate
from command_log import DIAGNOSTICS, record_exception, record_result
from ui_theme import make_button, setup_page
from usbip_manager import (build_usbipd_install_command, build_usbip_win2_install_command,
                           build_usbip_win2_uninstall_command)
from usbip_installer import find_client_installation, supported_architecture, InstallError


class ManagementTab(QWidget):
    def __init__(self, gate=None) -> None:
        super().__init__()
        self.gate = gate or OperationGate()
        self._process = None
        root = QVBoxLayout(self)
        setup_page(root)

        heading = QHBoxLayout()
        title = QLabel("Software components")
        title.setProperty("role", "heading")
        heading.addWidget(title)
        heading.addStretch()
        self.refresh_btn = make_button("Refresh status", "refresh")
        self.refresh_btn.clicked.connect(self.refresh_installation_status)
        heading.addWidget(self.refresh_btn)
        root.addLayout(heading)
        description = QLabel("Host PC: install usbipd-win. Client PC: install usbip-win2. Install both only if this PC has both roles.")
        description.setWordWrap(True)
        description.setProperty("role", "muted")
        root.addWidget(description)

        self.install_usbipd_btn = make_button("Install", "download")
        self.install_usbipd_btn.setProperty("primary", True)
        self.install_usbipd_btn.clicked.connect(self.install_usbipd)
        self.uninstall_usbipd_btn = make_button("Uninstall", "remove")
        self.uninstall_usbipd_btn.clicked.connect(self.uninstall_usbipd)
        self.install_usbip_win2_btn = make_button("Install", "download")
        self.install_usbip_win2_btn.setProperty("primary", True)
        self.install_usbip_win2_btn.clicked.connect(self.install_usbip_win2)
        self.uninstall_usbip_win2_btn = make_button("Uninstall", "remove")
        self.uninstall_usbip_win2_btn.clicked.connect(self.uninstall_usbip_win2)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        host_card, self.usbipd_status = self._component_card(
            "usbipd-win", "USB sharing service",
            "Share local USB devices with another system using USB/IP.",
            "Installation and removal may request administrator access.",
            [self.install_usbipd_btn, self.uninstall_usbipd_btn])
        client_card, self.usbip_win2_status = self._component_card(
            "usbip-win2", "Windows USB/IP client",
            "Connect Windows to USB devices shared by a remote host.",
            "Installs the latest stable release for this PC. USB devices may briefly reconnect; a restart may be required.",
            [self.install_usbip_win2_btn, self.uninstall_usbip_win2_btn])
        cards.addWidget(host_card, 1)
        cards.addWidget(client_card, 1)
        root.addLayout(cards)

        self.restore_check = QCheckBox("Create a restore point before installing usbip-win2 (recommended)")
        self.restore_check.setChecked(True)
        root.addWidget(self.restore_check)
        restore_help = QLabel(
            "usbip-win2 installs USB drivers. Its developers recommend a Windows restore point so you can "
            "roll back system changes if a driver causes problems. This uses Windows System Protection; "
            "it does not install another program or back up personal files. Administrator approval is required.")
        restore_help.setWordWrap(True)
        restore_help.setProperty("role", "muted")
        root.addWidget(restore_help)

        self.operation_status = QLabel("Ready")
        self.operation_status.setProperty("role", "muted")
        root.addWidget(self.operation_status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)

        log_header = QHBoxLayout()
        log_header.addWidget(QLabel("Activity log"))
        log_header.addStretch()
        self.export_btn = make_button("Export diagnostics", "save")
        self.export_btn.clicked.connect(self.export_diagnostics)
        self.clear_btn = make_button("Clear log", "clear")
        self.clear_btn.clicked.connect(lambda: self.log_widget.clear())
        log_header.addWidget(self.export_btn)
        log_header.addWidget(self.clear_btn)
        root.addLayout(log_header)
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.document().setMaximumBlockCount(300)
        self.log_widget.setPlaceholderText("Component actions and results will appear here.")
        root.addWidget(self.log_widget, 1)
        self.refresh_installation_status()
        self.gate.changed.connect(self.refresh_installation_status)

    @staticmethod
    def _component_card(title, subtitle, description, hint, buttons):
        card = QFrame()
        card.setProperty("role", "card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        header = QHBoxLayout()
        name = QLabel(title)
        name.setProperty("role", "cardTitle")
        header.addWidget(name)
        header.addStretch()
        badge = QLabel()
        badge.setProperty("role", "badge")
        header.addWidget(badge)
        layout.addLayout(header)
        for text in (subtitle, description):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setProperty("role", "muted")
            layout.addWidget(label)
        layout.addStretch()
        actions = QHBoxLayout()
        for button in buttons:
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        hint_label = QLabel(hint)
        hint_label.setWordWrap(True)
        hint_label.setProperty("role", "muted")
        layout.addWidget(hint_label)
        return card, badge

    def log(self, message: str) -> None:
        # Insert as plain text: command messages must never be interpreted as HTML.
        self.log_widget.moveCursor(self.log_widget.textCursor().MoveOperation.End)
        self.log_widget.insertPlainText(f"[{datetime.now():%H:%M:%S}] {message}\n")
        self.log_widget.ensureCursorVisible()

    @property
    def is_busy(self) -> bool:
        return self._process is not None

    @staticmethod
    def _component_detected(executable, directory):
        if shutil.which(executable):
            return True
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if base:
                root = Path(base) / "Programs" if variable == "LOCALAPPDATA" else Path(base)
                if (root / directory).is_dir():
                    return True
        return False

    def _is_usbipd_installed(self):
        return self._component_detected("usbipd", "usbipd-win")

    def _is_usbip_win2_installed(self):
        return find_client_installation() is not None

    def refresh_installation_status(self) -> None:
        host = self._is_usbipd_installed()
        client = self._is_usbip_win2_installed()
        for badge, detected in ((self.usbipd_status, host), (self.usbip_win2_status, client)):
            badge.setText("Detected" if detected else "Not detected")
            badge.setProperty("detected", detected)
            badge.setToolTip("Checks the registered installer." if badge is self.usbip_win2_status else
                             "Checks executable availability and standard installation folders.")
            badge.style().unpolish(badge)
            badge.style().polish(badge)
        busy = self._process is not None or not self.gate.available(self)
        self.install_usbipd_btn.setEnabled(not busy and not host)
        self.uninstall_usbipd_btn.setEnabled(not busy and host)
        try:
            supported_architecture()
            supported = True
            self.install_usbip_win2_btn.setToolTip("Download and install the latest stable official release.")
        except InstallError as error:
            supported = False
            self.install_usbip_win2_btn.setToolTip(str(error))
        self.install_usbip_win2_btn.setEnabled(not busy and not client and supported)
        installation = find_client_installation() if client else None
        self.uninstall_usbip_win2_btn.setEnabled(not busy and bool(installation and installation.uninstaller))
        self.uninstall_usbip_win2_btn.setToolTip("Uninstall usbip-win2." if installation and installation.uninstaller else
                                                "No registered usbip-win2 uninstaller was found.")
        self.refresh_btn.setEnabled(not busy)
        self.restore_check.setEnabled(not busy and not client)

    def _start_command(self, label, command, success_message=None, client_action=False):
        if self._process is not None:
            return
        if not self.gate.acquire(self):
            self.log("Wait for the current USB/IP or management action to finish.")
            return
        process = QProcess(self)
        self._process = process
        self._command = command
        self._label = label
        self._success_message = success_message
        self._client_action = client_action
        self._stdout = bytearray()
        self._pending_output = bytearray()
        process.readyReadStandardOutput.connect(self._read_output)
        process.finished.connect(self._command_finished)
        process.errorOccurred.connect(self._command_error)
        self.operation_status.setText(f"{label} in progress...")
        self.log(f"{label} started.")
        self.progress.show()
        self.refresh_installation_status()
        process.start(command[0], command[1:])

    def _read_output(self):
        chunk = bytes(self._process.readAllStandardOutput())
        self._stdout.extend(chunk)
        if not self._client_action:
            return
        self._pending_output.extend(chunk)
        while b"\n" in self._pending_output:
            line, _, remaining = self._pending_output.partition(b"\n")
            self._pending_output = bytearray(remaining)
            try:
                message = json.loads(line).get("message")
                if isinstance(message, str):
                    self.log(message)
                    self.operation_status.setText(message)
            except (ValueError, AttributeError):
                pass

    def _command_finished(self, exit_code, exit_status):
        process = self._process
        if process is None:
            return
        self._read_output()
        stdout = self._stdout.decode("utf-8", errors="replace")
        stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
        if exit_status == QProcess.ExitStatus.CrashExit and exit_code == 0:
            exit_code = -1
        reboot = self._client_action and exit_code == 3010
        message = record_result(self._label, self._command, exit_code, stdout, stderr)
        if reboot:
            message = "[OK] Action completed. Restart Windows to finish driver setup."
        self.log(message)
        if exit_code == 0 and self._success_message:
            self.log(self._success_message)
        self.operation_status.setText("Completed - restart Windows." if reboot else
                                     "Completed" if exit_code == 0 else "Action failed. See the activity log.")
        self._finish_command()
        if self._client_action and exit_code == 50 and "install" in self._command:
            if self._confirm_without_restore_point(failed=True):
                self._launch_client_install(create_restore=False)

    def _command_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self._process is not None:
            DIAGNOSTICS.append(f"{self._label}\n{self._command!r}\n{self._process.errorString()}\n")
            self.log(f"[ERROR] Could not start {self._command[0]}. Check installation and permissions.")
            self.operation_status.setText("Unable to start the action.")
            self._finish_command()

    def _finish_command(self):
        self._process.deleteLater()
        self._process = None
        self.gate.release(self)
        self.progress.hide()
        self.refresh_installation_status()

    def install_usbipd(self):
        self._start_command("Install usbipd-win", build_usbipd_install_command())

    def uninstall_usbipd(self):
        self._start_command("Uninstall usbipd-win", ["winget", "uninstall", "usbipd"])

    def install_usbip_win2(self):
        if self.is_busy or self._is_usbip_win2_installed():
            return
        create_restore = self.restore_check.isChecked()
        if not create_restore and not self._confirm_without_restore_point():
            return
        self._launch_client_install(create_restore)

    def _confirm_without_restore_point(self, failed=False):
        reason = ("A new restore point could not be verified. Driver installation has not started. "
                  "See the activity log for the reason. You can cancel, enable System Protection "
                  "in Windows (Create a restore point > Configure), and retry.\n\n" if failed else "")
        return QMessageBox.warning(
            self, "Install without a new restore point?",
            reason + "The usbip-win2 developers recommend a restore point before installing USB drivers. "
            "Without one, you may not be able to roll back these changes using System Restore.\n\n"
            "Continue installation without creating a new restore point?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def _launch_client_install(self, create_restore=True):
        command = build_usbip_win2_install_command()
        if not create_restore:
            command.append("--skip-restore-point")
        self._start_command("Install usbip-win2", command, client_action=True)

    def uninstall_usbip_win2(self):
        installation = find_client_installation()
        if self.is_busy or not installation or not installation.uninstaller:
            return
        self._start_command("Uninstall usbip-win2", build_usbip_win2_uninstall_command(), client_action=True)

    def export_diagnostics(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostics", "usbip-diagnostics.txt", "Text files (*.txt)",
            options=QFileDialog.Option.DontUseNativeDialog)
        if not filename:
            return
        try:
            Path(filename).write_text(
                "USB/IP Bridge diagnostics\nOriginal tool output may use the Windows language.\n\n"
                + "\n".join(DIAGNOSTICS), encoding="utf-8")
            self.log("[OK] Diagnostics exported.")
        except OSError as error:
            self.log(record_exception("Export diagnostics", ["file export"], error))
