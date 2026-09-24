"""Persistent settings for the optional metadata service."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QCheckBox, QLabel, QSpinBox, QPlainTextEdit, QGroupBox, QFormLayout, QTextEdit, QSizePolicy, QMessageBox
from ui_theme import setup_page, make_button
from device_metadata import authorized_addresses
from device_presentation import ActivityPanel, ContentScrollArea


class SettingsTab(QWidget):
    applied = pyqtSignal()

    def __init__(self, settings, service):
        super().__init__()
        self.settings, self.service = settings, service
        self._suggested_ips = set()
        self._access_dialog = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ContentScrollArea()
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        root = QVBoxLayout(content)
        setup_page(root)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)
        root.addWidget(QLabel("Device information"))
        self.share = QCheckBox("Share device names with clients")
        self.retrieve = QCheckBox("Retrieve device names from host")
        self.share.setChecked(str(settings.value("metadata/share", "false")).lower() == "true")
        self.retrieve.setChecked(str(settings.value("metadata/retrieve", "false")).lower() == "true")
        root.addWidget(self.share)
        root.addWidget(self.retrieve)
        note = QLabel("Optional name lookup; USB/IP connections work independently. "
                      "If the host does not provide names, Client keeps its current names.")
        note.setWordWrap(True)
        root.addWidget(note)
        advanced = QGroupBox("Advanced - network access")
        advanced.setStyleSheet("QGroupBox { padding: 0px; }")
        advanced.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(12, 24, 12, 12)
        advanced_layout.setSpacing(10)
        fields = QWidget()
        form = QFormLayout(fields)
        form.setContentsMargins(0, 0, 0, 0)
        advanced_layout.addWidget(fields)
        form.setVerticalSpacing(10)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        try:
            port = int(settings.value("metadata/port", 3241))
        except (ValueError, TypeError):
            port = 3241
        self.port.setValue(port if 1024 <= port <= 65535 and port != 3240 else 3241)
        form.addRow("Metadata port", self.port)
        self.allowed = QPlainTextEdit()
        self.allowed.setFixedHeight(90)
        self.allowed.setPlaceholderText("One authorized client IPv4 address per line; e.g. 192.168.1.20")
        self.allowed.setPlainText(str(settings.value("metadata/allowed", "")))
        form.addRow("Access control", self.allowed)
        warning = QLabel("Access is restricted by source IPv4 address, not user authentication. "
            "Names are sent over unencrypted HTTP. Use a trusted LAN or a protected VPN. "
            "No firewall rules are changed automatically. Allow this port on the host only for trusted clients. "
            "Use the same metadata port on both PCs; TCP 3240 is reserved for USB/IP.")
        warning.setWordWrap(True)
        warning.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        advanced_layout.addWidget(warning)
        root.addWidget(advanced)
        self.status = QLabel("Disabled")
        self.status.setWordWrap(True)
        service.status.connect(self.status.setText)
        root.addWidget(QLabel("Service status"))
        root.addWidget(self.status)
        apply = make_button("Apply settings", "save")
        apply.clicked.connect(self.apply)
        root.addWidget(apply)
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.document().setMaximumBlockCount(200)
        self.activity_panel = ActivityPanel(self.log_widget)
        root.addWidget(self.activity_panel)
        self.apply(save=False)

    def log(self, message):
        cursor = self.log_widget.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(message + "\n")
        self.log_widget.setTextCursor(cursor)
        self.activity_panel.update_message(message)

    def apply(self, checked=False, *, save=True):
        if save:
            self.log("> Apply settings")
        try:
            allowed = authorized_addresses(self.allowed.toPlainText())
            if self.port.value() == 3240:
                raise ValueError("Choose a metadata port different from USB/IP TCP 3240.")
            if self.share.isChecked() and not allowed:
                raise ValueError("Add at least one authorized client IPv4 address before sharing.")
        except ValueError as error:
            self.log("[ERROR] " + str(error))
            return
        if save:
            for key, value in (("share", self.share.isChecked()), ("retrieve", self.retrieve.isChecked()),
                               ("port", self.port.value()), ("allowed", self.allowed.toPlainText())):
                self.settings.setValue("metadata/" + key, value)
            self.settings.sync()
        self.service.configure(self.share.isChecked(), self.port.value(), allowed)
        if self.status.text().startswith("Error:"):
            self.log("[ERROR] " + self.status.text())
        elif save:
            self.log("[OK] Settings applied.")
        if save:
            self.log("Device name sharing: " + self.status.text())
            self.log("Remote name retrieval: " + ("Enabled. List remote devices in Client Mode to retrieve names."
                if self.retrieve.isChecked() else "Disabled."))
        self.applied.emit()

    def offer_host_access(self, host):
        import ipaddress
        try:
            address = ipaddress.ip_address(host.strip())
            if address.version != 4 or address.is_unspecified or address.is_multicast or address.is_loopback:
                return
            ip = str(address)
            saved = authorized_addresses(str(self.settings.value("metadata/allowed", "")))
            if ip in saved or ip in self._suggested_ips or self._access_dialog is not None:
                return
        except ValueError:
            return
        self._suggested_ips.add(ip)
        dialog = QMessageBox(self.window())
        dialog.setWindowTitle("Authorize device name access")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(f"Devices were found on {ip}. Add this IP to Access control?")
        dialog.setInformativeText("This allows that computer to retrieve device names from this PC when sharing is enabled. "
            "It does not authorize this PC on the remote host and does not enable sharing.")
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        self._access_dialog = dialog
        def finished(result):
            self._access_dialog = None
            if result == QMessageBox.StandardButton.Yes:
                self.add_authorized_ip(ip)
            dialog.deleteLater()
        dialog.finished.connect(finished)
        dialog.open()

    def add_authorized_ip(self, ip):
        # Save only this explicit permission, never apply unrelated draft settings.
        try:
            ip = next(iter(authorized_addresses(ip)))
            saved = authorized_addresses(str(self.settings.value("metadata/allowed", "")))
        except (ValueError, StopIteration):
            self.log("[ERROR] Unable to update Access control. Check saved IP addresses.")
            return
        saved.add(ip)
        self.settings.setValue("metadata/allowed", "\n".join(sorted(saved)))
        self.settings.sync()
        if self.settings.status() != self.settings.Status.NoError:
            self.log("[ERROR] Unable to save Access control.")
            return
        self.service.allowed = saved
        draft = self.allowed.toPlainText()
        if ip not in draft.replace(",", " ").split():
            self.allowed.setPlainText(draft.rstrip() + ("\n" if draft.strip() else "") + ip)
        self.log(f"[OK] {ip} added to Access control.")
