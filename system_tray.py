"""Tray lifetime and close choices; hiding never stops background work."""

from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QMenu, QMessageBox, QSystemTrayIcon


class SystemTray(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.restore_maximized = False
        self.icon = QSystemTrayIcon(window.windowIcon(), self)
        self.icon.setToolTip("USB/IP + Joystick Bridge - running")
        self.menu = QMenu(window)
        self.show_action = self.menu.addAction("Show application")
        self.show_action.triggered.connect(self.restore)
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("Exit application")
        self.exit_action.triggered.connect(window.request_exit)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        if self.available():
            self.icon.show()

    def available(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def hide_window(self):
        if not self.available():
            return False
        if not self.window.isMinimized():
            self.restore_maximized = self.window.isMaximized()
        self.icon.show()
        self.window.hide()
        return True

    def restore(self):
        if self.restore_maximized:
            self.window.showMaximized()
        else:
            self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore()

    def choose_close_action(self):
        dialog = QMessageBox(self.window)
        dialog.setWindowTitle("Close application")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("Keep the application running in the system tray, or exit completely?")
        dialog.setInformativeText(
            "System tray keeps background actions and controller monitoring running. "
            "Exit disconnects all imported USB/IP devices before closing. Devices shared in Host Mode stay shared.")
        tray = dialog.addButton("Send to System Tray", QMessageBox.ButtonRole.ActionRole)
        tray.setEnabled(self.available())
        exit_button = dialog.addButton("Exit application", QMessageBox.ButtonRole.DestructiveRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(tray if self.available() else cancel)
        dialog.setEscapeButton(cancel)
        dialog.exec()
        if dialog.clickedButton() is tray:
            return "tray"
        if dialog.clickedButton() is exit_button:
            return "exit"
        return "cancel"
