"""Executable entry point, including the isolated Management helper."""
import os
import sys


def main():
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
    from windowed_io import prepare_output
    prepare_output(helper=len(sys.argv) > 1 and sys.argv[1] == "--installer-helper")
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        # External Windows tools must use their own system DLL search path.
        import ctypes
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    if len(sys.argv) > 1 and sys.argv[1] == "--installer-helper":
        sys.argv.pop(1)
        from usbip_installer import main as installer_main
        return installer_main()
    if len(sys.argv) > 1 and sys.argv[1] == "--smoke-test":
        from PyQt6.QtWidgets import QApplication, QLabel
        from PyQt6.QtCore import QTimer
        from app_icon import application_icon
        import app
        application = QApplication([])
        icon = application_icon()
        if icon.isNull():
            return 2
        window = QLabel("USB/IP + Joystick Bridge - package check")
        window.setWindowIcon(icon)
        window.show()
        QTimer.singleShot(500, application.quit)
        return application.exec()
    from app import main as app_main
    app_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
