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


@pytest.fixture(autouse=True)
def isolated_preferences(monkeypatch, tmp_path):
    from PyQt6.QtCore import QSettings
    import app
    monkeypatch.setattr(app, "QSettings", type("IsolatedSettings", (), {
        "Status": QSettings.Status,
        "__new__": lambda cls, *args: QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    }))
