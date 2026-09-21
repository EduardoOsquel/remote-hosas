"""Compatibility entry point for the unified English-language interface."""

from app import UsbipJoystickBridgeApp, main

# Keep the previous window name available to existing launchers.
UsbipControllerApp = UsbipJoystickBridgeApp


if __name__ == "__main__":
    main()
