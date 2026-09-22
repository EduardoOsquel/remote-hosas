"""Serialize component and USB/IP commands across tabs."""
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

class OperationGate(QObject):
    changed = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.background = False
        self.starting_background = False
        self.pending_action = None
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


def defer_background_action(method):
    """Keep user actions responsive without overlapping a background query."""
    from functools import wraps
    import inspect
    positional_count = len(inspect.signature(method).parameters) - 1
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        args = args[:positional_count]
        gate = self.gate
        if gate.background and not gate.starting_background:
            if gate.pending_action is None:
                def retry():
                    if gate.background or gate.owner is not None:
                        QTimer.singleShot(25, retry)
                        return
                    gate.pending_action = None
                    method(self, *args, **kwargs)
                gate.pending_action = retry
                QTimer.singleShot(0, retry)
            return
        return method(self, *args, **kwargs)
    return wrapped
