from usbip_manager import (
    UsbipDevice,
    build_usbip_attach_command,
    build_usbip_detach_command,
    build_usbipd_bind_command,
    build_usbipd_unbind_command,
    parse_usbipd_list,
)


def test_parse_usbipd_list():
    sample = """
    BUSID  DEVICE
    3-2    USB Keyboard
    3-3.2  USB Camera
    """
    devices = parse_usbipd_list(sample)

    assert [device.busid for device in devices] == ["3-2", "3-3.2"]
    assert [device.name for device in devices] == ["USB Keyboard", "USB Camera"]


def test_build_usbipd_bind_command():
    cmd = build_usbipd_bind_command("3-2")

    assert cmd[0] == "usbipd"
    assert "--busid=3-2" in cmd


def test_build_usbip_attach_command():
    cmd = build_usbip_attach_command("192.168.1.5", "3-2")

    assert cmd == ["usbip", "--tcp-port=3240", "attach", "-r", "192.168.1.5", "-b", "3-2", "--once"]


def test_build_usbipd_unbind_command():
    cmd = build_usbipd_unbind_command("3-2")

    assert cmd[0] == "usbipd"
    assert "--busid=3-2" in cmd


def test_parse_usbipd_list_with_vid_pid_and_state():
    sample = """
    BUSID  VID:PID    DEVICE                                                        STATE
    1-1    046d:c548  Logitech USB Input Device, Dispositivo de entrada USB         Not shared
    1-3    05c8:0b10  HP True Vision HD Camera, APP Mode                            Not shared
    1-10   0bda:b85c  Realtek Wireless Bluetooth Adapter                            Not shared
    4-4    0bda:8153  Realtek USB GbE Family Controller                             Not shared
    GUID                                  DEVICE
    7d3a5d11-...                          Something fake
    """
    devices = parse_usbipd_list(sample)

    assert len(devices) == 4
    assert devices[0].busid == "1-1"
    assert devices[0].vid_pid == "046d:c548"
    assert "Logitech USB Input Device" in devices[0].name
    assert devices[0].state == "Not shared"


def test_build_usbip_detach_command():
    cmd = build_usbip_detach_command("1")

    assert cmd == ["usbip", "detach", "-p", "1"]


def test_parse_attached_and_forced_host_states():
    devices = parse_usbipd_list("1-1 1234:5678 Game controller Attached\n1-2 1234:5679 USB Keyboard Shared (forced)")
    assert [(d.name, d.state) for d in devices] == [("Game controller", "Attached"), ("USB Keyboard", "Shared (forced)")]


def test_remote_and_imported_device_formats():
    from usbip_manager import parse_remote_devices, parse_imported_devices
    remote = parse_remote_devices("""Exportable USB devices
       1-3 : Logitech controller (046d:c548)
           : /sys/devices/usb1/1-3
           : (Defined at Interface level) (00/00/00)
           :  0 - Human Interface Device
       2-4.1: Camera (1234:5678)
""")
    assert [d.busid for d in remote] == ["1-3", "2-4.1"]
    imported = parse_imported_devices("""Imported USB devices
Port 01: device in use at high-speed
         Logitech controller (046d:c548)
           -> usbip://192.168.1.20:3240/1-3
           -> remote bus/dev: 001/003
Port 12: device in use at full-speed
         Camera
           -> usbip://other-host:3240/2-4.1
""")
    assert [d.port for d in imported] == [1, 12]
    assert imported[0].name == "Logitech controller (046d:c548)"
    assert imported[0].location == "192.168.1.20:3240/1-3"


def test_tcp_port_is_not_a_detach_port():
    import pytest
    from usbip_manager import build_usbip_list_command
    assert build_usbip_list_command("my-host", 4000) == ["usbip", "--tcp-port=4000", "list", "-r", "my-host"]
    with pytest.raises(ValueError):
        build_usbip_detach_command("3240")
