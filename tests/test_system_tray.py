import os
from subprocess import CompletedProcess
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication

from app import UsbipJoystickBridgeApp
from system_tray import SystemTray


@pytest.fixture
def window():
    application = QApplication.instance() or QApplication([])
    with patch("app.subprocess.run", return_value=CompletedProcess([], 0, "", "")), \
            patch("app.pygame", None), \
            patch.object(SystemTray, "available", return_value=True), \
            patch("system_tray.QSystemTrayIcon.show"), \
            patch("system_tray.QSystemTrayIcon.hide"), \
            patch.object(application, "quit") as quit_app:
        widget = UsbipJoystickBridgeApp()
        widget.show()
        application.processEvents()
        with patch.object(widget.client_tab, "disconnect_before_exit", side_effect=lambda done: done(True)):
            yield application, widget, quit_app
        widget.hide()
        widget.deleteLater()
        application.processEvents()


def test_minimize_hides_and_restore_keeps_maximized_state(window):
    application, widget, quit_app = window
    widget.showMaximized()
    application.processEvents()
    widget.showMinimized()
    application.processEvents()
    assert not widget.isVisible()
    quit_app.assert_not_called()
    widget.tray.show_action.trigger()
    application.processEvents()
    assert widget.isVisible()
    assert widget.isMaximized()


@pytest.mark.parametrize("choice", ["tray", "cancel", "exit"])
def test_close_choices(window, choice):
    _, widget, quit_app = window
    event = QCloseEvent()
    with patch.object(widget.tray, "choose_close_action", return_value=choice):
        widget.closeEvent(event)
    assert not event.isAccepted()  # Exit completes through a second close after cleanup.
    if choice == "exit":
        quit_app.assert_called_once()
    else:
        quit_app.assert_not_called()
        assert widget.isVisible() == (choice == "cancel")


def test_busy_installation_can_be_hidden_but_cannot_be_terminated(window):
    _, widget, quit_app = window
    widget.management_tab._process = object()
    with patch.object(widget.tray, "choose_close_action", return_value="tray"):
        widget.closeEvent(QCloseEvent())
    assert not widget.isVisible()
    widget.tray.exit_action.trigger()
    assert widget.isVisible()
    assert not widget._exit_requested
    quit_app.assert_not_called()
    widget.management_tab._process = None


def test_unavailable_tray_does_not_hide_window(window):
    _, widget, _ = window
    with patch.object(widget.tray, "available", return_value=False):
        assert not widget.tray.hide_window()
    assert widget.isVisible()


def test_tray_exit_exits_without_showing_close_choice_again(window):
    _, widget, quit_app = window
    widget.tray.hide_window()
    with patch.object(widget.tray, "choose_close_action") as choose:
        widget.tray.exit_action.trigger()
        choose.assert_not_called()
    quit_app.assert_called_once()


def test_exit_waits_for_disconnect_and_keeps_window_on_failure(window):
    _, widget, quit_app = window
    callbacks = []
    with patch.object(widget.client_tab, "disconnect_before_exit", side_effect=callbacks.append):
        widget.request_exit()
    quit_app.assert_not_called()
    assert widget._shutdown_pending
    callbacks[0](False)
    assert not widget._shutdown_pending
    assert widget.isVisible()
    quit_app.assert_not_called()
