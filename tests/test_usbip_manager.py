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

    assert cmd[0] == "usbipd"
    assert "--wsl" in cmd
    assert "--busid=3-2" in cmd
    assert "--host=192.168.1.5" in cmd


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

    assert cmd[0] == "usbipd"
    assert "--port=1" in cmd
