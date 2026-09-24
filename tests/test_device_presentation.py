import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication, QTextEdit
from device_presentation import ActivityPanel
from client_ui import ClientModeTab
from usbip_manager import ImportedDevice, UsbipDevice


def test_collapsed_activity_keeps_errors_visible():
    application = QApplication.instance() or QApplication([])
    panel = ActivityPanel(QTextEdit())
    assert panel.editor.isHidden()
    panel.update_message("[ERROR] Connection failed")
    panel.update_message("Check the host address")
    assert not panel.error.isHidden()
    assert "Connection failed" in panel.error.text()
    panel.toggle.click()
    assert not panel.editor.isHidden()
    panel.deleteLater()


def test_client_details_follow_selection_and_clear_on_endpoint_change():
    application = QApplication.instance() or QApplication([])
    widget = ClientModeTab()
    widget.host_input.setText("192.168.1.10")
    widget.devices = [UsbipDevice("1-2", "Camera", "1234:5678")]
    widget.device_combo.clear()
    widget.device_combo.addItem("Camera", "1-2")
    assert "1234:5678" in widget.remote_details.text()
    assert "192.168.1.10:3240" in widget.remote_details.text()
    widget.host_input.setText("other-host")
    assert "Camera" not in widget.remote_details.text()
    widget._set_imported([ImportedDevice(2, "Camera", "usbip://host/1-2")])
    assert "usbip://host/1-2" in widget.imported_details.text()
    assert not widget.port_input.itemIcon(0).isNull()
    widget._set_imported([])
    assert "Camera" not in widget.imported_details.text()
    widget.deleteLater()


def test_activity_disclosure_uses_fixed_title_and_arrow():
    from PyQt6.QtCore import Qt
    application = QApplication.instance() or QApplication([])
    panel = ActivityPanel(QTextEdit())
    assert panel.toggle.text() == "Activity log"
    assert panel.toggle.arrowType() == Qt.ArrowType.RightArrow
    panel.toggle.click()
    assert panel.toggle.text() == "Activity log"
    assert panel.toggle.arrowType() == Qt.ArrowType.DownArrow
    panel.deleteLater()


def test_client_details_do_not_overlap_actions_at_small_size():
    from PyQt6.QtWidgets import QScrollArea
    from ui_theme import APP_STYLESHEET
    application = QApplication.instance() or QApplication([])
    widget = ClientModeTab()
    widget.setStyleSheet(APP_STYLESHEET)
    widget.resize(900, 600)
    widget.remote_details.setText("Long device name " * 20 + "\nExported by host:3240\nBUSID: 2-3")
    widget.show()
    application.processEvents()
    from PyQt6.QtCore import QPoint
    detail_bottom = widget.remote_details.mapTo(widget, QPoint(0, widget.remote_details.height())).y()
    action_top = widget.list_btn.mapTo(widget, QPoint(0, 0)).y()
    assert action_top > detail_bottom
    assert widget.findChild(QScrollArea).verticalScrollBar().maximum() > 0
    widget.close()
    widget.deleteLater()


def test_compact_client_exposes_activity_header_at_desktop_size():
    from PyQt6.QtWidgets import QScrollArea
    from ui_theme import APP_STYLESHEET
    from PyQt6.QtCore import QPoint
    application = QApplication.instance() or QApplication([])
    widget = ClientModeTab()
    widget.setStyleSheet(APP_STYLESHEET)
    widget.resize(1400, 900)
    widget.show()
    application.processEvents()
    scroll = widget.findChild(QScrollArea)
    assert scroll.verticalScrollBar().maximum() == 0
    header = widget.activity_panel.toggle
    assert header.mapTo(widget, QPoint(0, header.height())).y() < widget.height()
    widget.close()
    widget.deleteLater()


def test_repeated_disclosure_releases_scroll_range_and_keeps_width():
    from device_presentation import ContentScrollArea
    from ui_theme import APP_STYLESHEET
    application = QApplication.instance() or QApplication([])
    widget = ClientModeTab()
    widget.setStyleSheet(APP_STYLESHEET)
    widget.resize(1400, 780)
    widget.show()
    for _ in range(3):
        application.processEvents()
    scroll = widget.findChild(ContentScrollArea)
    initial = (scroll.widget().size(), scroll.verticalScrollBar().maximum())
    for _ in range(6):
        widget.activity_panel.toggle.click()
        for _ in range(3):
            application.processEvents()
        assert scroll.widget().width() == initial[0].width()
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        widget.activity_panel.toggle.click()
        for _ in range(3):
            application.processEvents()
        assert scroll.widget().size() == initial[0]
        assert scroll.verticalScrollBar().maximum() == initial[1]
    widget.close()
    widget.deleteLater()


def test_activity_summary_uses_same_operation_policy_for_both_tabs():
    application = QApplication.instance() or QApplication([])
    for detail in ("Shared host devices: 1. Sharing remains enabled when this application exits.",
                   "Detected 1 exportable USB device(s) on host:3240."):
        panel = ActivityPanel(QTextEdit())
        panel.update_message("> List devices")
        assert panel.summary.text() == "In progress: List devices"
        panel.update_message("[OK] List devices completed.")
        panel.update_message(detail)
        assert panel.summary.text() == "[OK] List devices completed."
        panel.update_message("[ERROR] List devices failed")
        panel.update_message("Check the host address")
        assert "failed" in panel.summary.text()
        assert not panel.error.isHidden()
        panel.update_message("[OK] List devices completed.")
        assert panel.error.isHidden()
        panel.deleteLater()
