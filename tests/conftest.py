"""Existing UI tests simulate host completion; worker tests exercise threads separately."""
import pytest
from PyQt6.QtCore import QObject, pyqtSignal

@pytest.fixture(autouse=True)
def simulated_host_worker(monkeypatch):
    import app
    class Worker(QObject):
        finished = pyqtSignal()
        def __init__(self, command, parent=None):
            super().__init__(parent)
            self.command = command
            self.result = self.error = None
        def start(self):
            try:
                self.result = app.subprocess.run(self.command, capture_output=True, text=True)
            except Exception as error:
                self.error = error
            self.finished.emit()
    monkeypatch.setattr(app, "HostWorker", Worker)
