from joystick_bridge import JoystickPacket, JoystickState


def test_joystick_packet_roundtrip():
    state = JoystickState(
        axes=[0.1, -0.2, 0.3, -0.4],
        buttons=[True, False, True, False, False, False, False, False],
        hats=[(0, 1)],
    )

    packet = JoystickPacket.from_state(state)
    restored = JoystickPacket.to_state(packet)

    assert restored.axes == state.axes
    assert restored.buttons == state.buttons
    assert restored.hats == state.hats


def test_joystick_packet_has_metadata():
    packet = JoystickPacket.from_state(JoystickState(axes=[0.0], buttons=[], hats=[]))

    assert packet["version"] == 1
    assert packet["axes"] == [0.0]
    assert packet["buttons"] == []
    assert packet["hats"] == []
