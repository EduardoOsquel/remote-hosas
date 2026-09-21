"""Dependency management UI; external commands run without blocking Qt."""

import os
import shutil
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QProcess, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QTextEdit,
    QVBoxLayout, QWidget,
)

from command_log import DIAGNOSTICS, record_exception, record_result
from ui_theme import make_button, setup_page
from usbip_manager import build_usbipd_install_command


class ManagementTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
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
        description = QLabel("Manage the tools used to share and connect USB devices.")
        description.setProperty("role", "muted")
        root.addWidget(description)

        self.install_usbipd_btn = make_button("Install", "download")
        self.install_usbipd_btn.setProperty("primary", True)
        self.install_usbipd_btn.clicked.connect(self.install_usbipd)
        self.uninstall_usbipd_btn = make_button("Uninstall", "remove")
        self.uninstall_usbipd_btn.clicked.connect(self.uninstall_usbipd)
        self.install_usbip_win2_btn = make_button("Open downloads", "external")
        self.install_usbip_win2_btn.clicked.connect(self.install_usbip_win2)
        self.uninstall_usbip_win2_btn = make_button("Open uninstaller", "external")
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
            "Download and install manually, then refresh the status.",
            [self.install_usbip_win2_btn, self.uninstall_usbip_win2_btn])
        cards.addWidget(host_card, 1)
        cards.addWidget(client_card, 1)
        root.addLayout(cards)

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
        return self._component_detected("usbip", "usbip-win2")

    def refresh_installation_status(self) -> None:
        host = self._is_usbipd_installed()
        client = self._is_usbip_win2_installed()
        for badge, detected in ((self.usbipd_status, host), (self.usbip_win2_status, client)):
            badge.setText("Detected" if detected else "Not detected")
            badge.setProperty("detected", detected)
            badge.setToolTip("Checks executable availability and standard installation folders.")
            badge.style().unpolish(badge)
            badge.style().polish(badge)
        busy = self._process is not None
        self.install_usbipd_btn.setEnabled(not busy and not host)
        self.uninstall_usbipd_btn.setEnabled(not busy and host)
        self.install_usbip_win2_btn.setEnabled(not busy)
        self.uninstall_usbip_win2_btn.setEnabled(not busy)
        self.refresh_btn.setEnabled(not busy)

    def _start_command(self, label, command, success_message=None):
        if self._process is not None:
            return
        process = QProcess(self)
        self._process = process
        self._command = command
        self._label = label
        self._success_message = success_message
        process.finished.connect(self._command_finished)
        process.errorOccurred.connect(self._command_error)
        self.operation_status.setText(f"{label} in progress...")
        self.log(f"{label} started.")
        self.progress.show()
        self.refresh_installation_status()
        process.start(command[0], command[1:])

    def _command_finished(self, exit_code, exit_status):
        process = self._process
        if process is None:
            return
        stdout = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
        if exit_status == QProcess.ExitStatus.CrashExit and exit_code == 0:
            exit_code = -1
        message = record_result(self._label, self._command, exit_code, stdout, stderr)
        self.log(message)
        if exit_code == 0 and self._success_message:
            self.log(self._success_message)
        self.operation_status.setText("Completed" if exit_code == 0 else "Action failed. See the activity log.")
        self._finish_command()

    def _command_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self._process is not None:
            DIAGNOSTICS.append(f"{self._label}\n{self._command!r}\n{self._process.errorString()}\n")
            self.log(f"[ERROR] Could not start {self._command[0]}. Check installation and permissions.")
            self.operation_status.setText("Unable to start the action.")
            self._finish_command()

    def _finish_command(self):
        self._process.deleteLater()
        self._process = None
        self.progress.hide()
        self.refresh_installation_status()

    def install_usbipd(self):
        self._start_command("Install usbipd-win", build_usbipd_install_command())

    def uninstall_usbipd(self):
        self._start_command("Uninstall usbipd-win", ["winget", "uninstall", "usbipd"])

    def install_usbip_win2(self):
        url = QUrl("https://github.com/vadimgrn/usbip-win2/releases/latest")
        if QDesktopServices.openUrl(url):
            self.log("[OK] Download page opened. Install usbip-win2, then select Refresh status.")
        else:
            self.log("[ERROR] Could not open the download page in your browser.")

    def uninstall_usbip_win2(self):
        self._start_command("Open Windows uninstaller", ["control.exe", "appwiz.cpl"],
                            "Select usbip-win2 in Windows to uninstall it, then refresh the status.")

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
