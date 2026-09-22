"""Serialize component and USB/IP commands across tabs."""
from PyQt6.QtCore import QObject, pyqtSignal

class OperationGate(QObject):
    changed = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.owner = None
    def acquire(self, owner):
        if self.owner is not None:
            return False
        self.owner = owner
        self.changed.emit()
        return True
    def release(self, owner):
        if self.owner is owner:
            self.owner = None
            self.changed.emit()
    def available(self, owner):
        return self.owner is None or self.owner is owner
