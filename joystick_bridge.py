from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class JoystickState:
    axes: List[float] = field(default_factory=list)
    buttons: List[bool] = field(default_factory=list)
    hats: List[Tuple[int, int]] = field(default_factory=list)


class JoystickPacket(dict):
    version = 1

    @classmethod
    def from_state(cls, state: JoystickState) -> "JoystickPacket":
        return cls(
            version=cls.version,
            axes=[float(v) for v in state.axes],
            buttons=[bool(v) for v in state.buttons],
            hats=[(int(x), int(y)) for x, y in state.hats],
        )

    @staticmethod
    def to_state(packet: dict) -> JoystickState:
        return JoystickState(
            axes=[float(v) for v in packet.get("axes", [])],
            buttons=[bool(v) for v in packet.get("buttons", [])],
            hats=[(int(x), int(y)) for x, y in packet.get("hats", [])],
        )
