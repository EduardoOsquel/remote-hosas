"""Optional, read-only device names service. Never executes USB/IP commands."""
import ipaddress
import json
import re
from dataclasses import replace
from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import (QTcpServer, QHostAddress, QNetworkAccessManager,
                            QNetworkRequest, QNetworkReply, QNetworkProxy)

MAX_BYTES = 65536
PATH = "/v1/device-names"


def authorized_addresses(text):
    result = set()
    for value in text.replace(",", " ").split():
        address = ipaddress.ip_address(value)
        if address.version != 4:
            raise ValueError("Only individual IPv4 addresses are supported.")
        result.add(str(address))
    return result


def merge_names(devices, payload):
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return devices
    records = payload.get("devices")
    if not isinstance(records, list) or len(records) > 512:
        return devices
    names = {}
    duplicates = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        busid, ids, name = (record.get(k) for k in ("busid", "vid_pid", "name"))
        if not all(isinstance(v, str) for v in (busid, ids, name)):
            continue
        if not re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}", ids):
            continue
        if not name.strip() or len(name) > 256 or any(ord(c) < 32 for c in name):
            continue
        key = (busid, ids.lower())
        if key in names:
            duplicates.add(key)
        names[key] = name.strip()
    return [replace(d, name=names[(d.busid, d.vid_pid.lower())])
            if (d.busid, d.vid_pid.lower()) in names and (d.busid, d.vid_pid.lower()) not in duplicates
            else d for d in devices]


class MetadataService(QObject):
    status = pyqtSignal(str)

    def __init__(self, devices, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.allowed = set()
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self.accept_connections)
        self.sockets = set()

    def stop(self):
        self.server.close()
        for socket in list(self.sockets):
            socket.abort()
        self.status.emit("Disabled")

    def configure(self, enabled, port, allowed):
        self.stop()
        self.allowed = allowed
        if not enabled:
            return
        if not allowed:
            self.status.emit("Error: add at least one authorized client IPv4 address.")
            return
        if not self.server.listen(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), port):
            self.status.emit("Error: " + self.server.errorString())
            return
        self.status.emit(f"Listening on TCP {self.server.serverPort()} (IPv4; authorized clients only)")

    def accept_connections(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket.peerAddress().toString() not in self.allowed or len(self.sockets) >= 8:
                socket.abort()
                socket.deleteLater()
                continue
            self.sockets.add(socket)
            socket.setReadBufferSize(4097)
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(2000)
            socket.readyRead.connect(lambda s=socket: self.read_request(s))
            socket.disconnected.connect(lambda s=socket: self.release(s))

    def release(self, socket):
        self.sockets.discard(socket)
        socket.deleteLater()

    def read_request(self, socket):
        request = bytes(socket.peek(4097))
        if len(request) > 4096:
            socket.abort()
            return
        if b"\r\n\r\n" not in request:
            return
        socket.readAll()
        if request.split(b"\r\n", 1)[0] != b"GET /v1/device-names HTTP/1.1":
            socket.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        else:
            records = [{"busid": d.busid, "vid_pid": d.vid_pid, "name": d.name[:256]}
                       for d in self.devices() if d.state in {"Shared", "Shared (forced)", "Attached"}][:512]
            body = json.dumps({"version": 1, "devices": records}, ensure_ascii=True).encode("ascii")
            if len(body) > MAX_BYTES:
                socket.abort()
                return
            socket.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nCache-Control: no-store\r\nConnection: close\r\nContent-Length: "
                         + str(len(body)).encode() + b"\r\n\r\n" + body)
        socket.disconnectFromHost()


class MetadataClient(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self.manager.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.reply = None
        self.generation = 0

    def cancel(self):
        self.generation += 1
        if self.reply is not None:
            self.reply.abort()
            self.reply = None

    def fetch(self, host, port, callback):
        self.cancel()
        generation = self.generation
        url = QUrl()
        url.setScheme("http")
        url.setHost(host.strip("[]"))
        url.setPort(port)
        url.setPath(PATH)
        request = QNetworkRequest(url)
        request.setTransferTimeout(2000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        reply = self.manager.get(request)
        self.reply = reply
        buffer = bytearray()
        timer = QTimer(reply)
        timer.setSingleShot(True)
        timer.timeout.connect(reply.abort)
        timer.start(2000)
        def read():
            buffer.extend(bytes(reply.readAll()))
            if len(buffer) > MAX_BYTES:
                reply.abort()
        reply.readyRead.connect(read)
        def finished():
            timer.stop()
            read()
            payload = None
            if generation == self.generation and reply.error() == QNetworkReply.NetworkError.NoError:
                try:
                    payload = json.loads(buffer)
                except (ValueError, UnicodeError):
                    pass
            if self.reply is reply:
                self.reply = None
            reply.deleteLater()
            if generation == self.generation:
                callback(payload)
        reply.finished.connect(finished)
