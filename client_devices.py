"""Unified client device table and endpoint-aware connection matching."""
from urllib.parse import urlsplit
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
from ui_icons import line_icon, device_icon_kind
from ui_theme import DeviceStateDelegate


def imported_endpoint(location):
    try:
        url = urlsplit(location if "://" in location else "usbip://" + location)
        host = (url.hostname or "").casefold().rstrip(".")
        if host in {"localhost", "::1"}:
            host = "127.0.0.1"
        return host, url.port or 3240, url.path.strip("/")
    except ValueError:
        return None


class ClientDevices:
    def setup_device_table(self):
        self._building_table = False
        self._table_rows = []
        self.device_table = QTableWidget(0, 3)
        table = self.device_table
        table.setHorizontalHeaderLabels(["DEVICE", "STATE", "BUSID"])
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(38)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(False)
        table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
        table.setSelectionMode(table.SelectionMode.SingleSelection)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)
        table.setItemDelegateForColumn(1, DeviceStateDelegate(table))
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(3):
            table.horizontalHeaderItem(i).setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if i == 0 else Qt.AlignmentFlag.AlignCenter)
        table.itemSelectionChanged.connect(self.table_selected)
        self.connected_table = QTableWidget(0, 3)
        connected = self.connected_table
        connected.setHorizontalHeaderLabels(["DEVICE", "HOST", "BUSID"])
        for column in range(3):
            connected.horizontalHeaderItem(column).setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                if column == 0 else Qt.AlignmentFlag.AlignCenter)
        connected.verticalHeader().hide()
        connected.verticalHeader().setDefaultSectionSize(38)
        connected.setSelectionBehavior(connected.SelectionBehavior.SelectRows)
        connected.setSelectionMode(connected.SelectionMode.SingleSelection)
        connected.setEditTriggers(connected.EditTrigger.NoEditTriggers)
        connected.setAlternatingRowColors(True)
        connected.setShowGrid(False)
        connected.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        connected.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        connected.itemSelectionChanged.connect(self.connected_selected)
        self._selected_connection = None
        return table

    def showEvent(self, event):
        super().showEvent(event)
        table = self.device_table
        table.setFixedHeight(table.horizontalHeader().sizeHint().height() + 4 * 38 + 2 * table.frameWidth())

    def rebuild_device_table(self):
        if self._building_table:
            return
        self._building_table = True
        try:
            old = self.device_table.currentRow()
            selected = self._table_rows[old][0] if 0 <= old < len(self._table_rows) else None
            host, port = self._endpoint()
            endpoint = imported_endpoint(f"{host}:{port}/")
            rows, used = [], set()
            for device in self.devices:
                match = next((d for d in self.imported_devices if endpoint and
                    imported_endpoint(d.location) == (*endpoint[:2], device.busid)), None)
                if match:
                    used.add(match.port)
                rows.append(((host, port, device.busid), device, match))
            self._table_rows = rows
            table = self.device_table
            table.blockSignals(True)
            table.setRowCount(len(rows))
            for i, (_, remote, local) in enumerate(rows):
                name = remote.name if remote else local.name
                location = imported_endpoint(local.location) if local else None
                busid = remote.busid if remote else (location[2] if location else "-")
                for col, value in enumerate((name, "Connected" if local else "Not connected", busid)):
                    item = QTableWidgetItem(value)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if col == 0 else Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(value + ("\nSource: " + local.location if local else ""))
                    if col == 0:
                        item.setIcon(line_icon(device_icon_kind(name)))
                    table.setItem(i, col, item)
            if rows and self._selected_connection is None:
                table.selectRow(next((i for i,r in enumerate(rows) if r[0] == selected), 0))
            table.blockSignals(False)
        finally:
            self._building_table = False
        self.rebuild_connections()
        if self._selected_connection is None:
            self.table_selected()

    def table_selected(self):
        if self._building_table:
            return
        if not self.device_table.selectedItems():
            return
        self._selected_connection = None
        self.connected_table.blockSignals(True)
        self.connected_table.clearSelection()
        self.connected_table.blockSignals(False)
        index = self.device_table.currentRow()
        if not 0 <= index < len(self._table_rows):
            self.remote_details.setText("List devices or refresh connections to select a device.")
            return
        _, remote, local = self._table_rows[index]
        self.device_combo.setCurrentIndex(self.device_combo.findData(remote.busid) if remote else -1)
        self.port_input.setCurrentIndex(self.port_input.findData(local.port) if local else -1)
        name = remote.name if remote else local.name
        source = local.location if local else f"{self.host_input.text()}:{self.tcp_port_input.value()}"
        self.remote_details.setText(f"{name}\n{'Connected to this PC' if local else 'Not connected to this PC'} | Source: {source}\n"
            + (f"VID:PID: {remote.vid_pid or '-'}" if remote else "VID:PID: Not reported")
            + (f" | Virtual USB port: {local.port}" if local else ""))
        self._update_controls()

    def rebuild_connections(self):
        table = self.connected_table
        table.blockSignals(True)
        table.setRowCount(len(self.imported_devices))
        selected = -1
        for i, device in enumerate(self.imported_devices):
            endpoint = imported_endpoint(device.location)
            source = f"{endpoint[0]}:{endpoint[1]}" if endpoint else device.location
            for col, text in enumerate((device.name, source, endpoint[2] if endpoint else "-")):
                item = QTableWidgetItem(text)
                item.setToolTip(device.location)
                if col == 0:
                    item.setIcon(line_icon(device_icon_kind(device.name)))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(i, col, item)
            if self._selected_connection == (device.port, device.location):
                selected = i
        table.setFixedHeight(table.horizontalHeader().sizeHint().height() + 38 * max(1, min(3, len(self.imported_devices))) + 2 * table.frameWidth())
        if selected >= 0:
            table.selectRow(selected)
        table.blockSignals(False)
        if selected >= 0:
            self.connected_selected()
        elif self._selected_connection is not None:
            self._selected_connection = None
            self.port_input.setCurrentIndex(-1)
            self.device_combo.setCurrentIndex(-1)
            self.remote_details.setText("Select a device to see its details.")
            self._update_controls()

    def connected_selected(self):
        if self._building_table or not self.connected_table.selectedItems():
            return
        index = self.connected_table.currentRow()
        if not 0 <= index < len(self.imported_devices):
            return
        device = self.imported_devices[index]
        self._selected_connection = (device.port, device.location)
        self.device_table.blockSignals(True)
        self.device_table.clearSelection()
        self.device_table.blockSignals(False)
        self.device_combo.setCurrentIndex(-1)
        self.port_input.setCurrentIndex(self.port_input.findData(device.port))
        self.remote_details.setText(f"{device.name}\nConnected to this PC | Source: {device.location}\nVirtual USB port: {device.port}")
        self._update_controls()
