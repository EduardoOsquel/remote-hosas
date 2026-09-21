"""Exercise refresh and selection without accessing USB hardware."""
import os
from subprocess import CompletedProcess
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from app import HostModeTab
from ui_theme import APP_STYLESHEET


OUTPUT = """Connected:
BUSID VID:PID DEVICE STATE
1-1 046d:c548 Logitech USB Input Device Not shared
1-3 05c8:0b10 HP True Vision HD Camera Not shared
"""


@pytest.fixture
def host():
    application = QApplication.instance() or QApplication([])
    application.setStyle("Fusion")
    with patch("app.subprocess.run", return_value=CompletedProcess([], 0, OUTPUT, "")) as command:
        widget = HostModeTab()
        widget.setStyleSheet(APP_STYLESHEET)
        widget.resize(1100, 750)
        widget.show()
        application.processEvents()
        yield application, widget, command
        widget.close()
        widget.deleteLater()
        application.processEvents()


def test_refresh_fills_available_width_after_maximizing(host):
    application, widget, command = host
    widget.showMaximized()
    application.processEvents()
    widget.list_btn.click()
    application.processEvents()
    assert abs(sum(widget.device_table.columnWidth(i) for i in range(4))
               - widget.device_table.viewport().width()) <= 2
    # Also exercise a wide viewport independently of the offscreen screen size.
    widget.showNormal()
    widget.resize(1900, 1000)
    application.processEvents()
    table = widget.device_table
    before = (table.width(), table.height(), table.columnWidth(2))
    for _ in range(3):
        command.reset_mock()
        widget.list_btn.click()
        application.processEvents()
        assert command.call_count == 1
        assert (table.width(), table.height(), table.columnWidth(2)) == before
        assert abs(sum(table.columnWidth(i) for i in range(4)) - table.viewport().width()) <= 2


def test_selection_is_synchronized_preserved_and_used_for_bind(host):
    application, widget, command = host
    widget.device_table.selectRow(1)
    assert widget.device_combo.currentData() == "1-3"
    command.return_value = CompletedProcess([], 0, OUTPUT.replace(
        "1-1 046d:c548 Logitech USB Input Device Not shared\n", ""), "")
    widget.refresh_usbipd_devices()
    assert widget.device_combo.currentData() == "1-3"
    assert widget.device_table.currentRow() == 0
    widget.bind_btn.click()
    assert command.call_args.args[0] == ["usbipd", "bind", "--busid=1-3"]


@pytest.mark.parametrize("failure", [False, True, "missing"])
def test_empty_or_failed_refresh_removes_stale_devices(host, failure):
    application, widget, command = host
    if failure == "missing":
        command.side_effect = FileNotFoundError("usbipd")
    else:
        command.return_value = CompletedProcess([], int(failure), "", "List failed" if failure else "")
    widget.refresh_usbipd_devices()
    assert widget.devices == []
    assert widget.device_table.rowCount() == 0
    assert not widget.bind_btn.isEnabled()
    assert not widget.unbind_btn.isEnabled()
