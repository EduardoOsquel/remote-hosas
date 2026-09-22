"""Small vector icons drawn in the application's own visual language."""

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


PATHS = {
    "usb": '<path d="M12 21V3m-3 3 3-3 3 3M12 16l-6-4V9m6 4 6-4V6"/><circle cx="6" cy="7" r="2"/><path d="M16 3h4v3h-4z"/>',
    "mouse": '<rect x="6" y="2" width="12" height="20" rx="6"/><path d="M12 3v6M6 10h12"/>',
    "keyboard": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M5 9h1m3 0h1m3 0h1m3 0h2M5 12h1m3 0h1m3 0h1m3 0h2M7 16h10"/>',
    "gaming": '<path d="M7 7h10c3 0 4 4 5 10 0 3-3 4-5 0l-1-1H8l-1 1c-2 4-5 3-5 0 1-6 2-10 5-10zM7 9v6m-3-3h6M16 10h.1M19 13h.1"/>',
    "camera": '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="m7 6 2-3h6l2 3"/><circle cx="12" cy="13" r="4"/>',
    "network": '<rect x="7" y="2" width="10" height="6" rx="1"/><path d="M12 8v5M4 17v-4h16v4M12 13v4"/><path d="M2 17h4v4H2zM10 17h4v4h-4zM18 17h4v4h-4z"/>',
    "audio": '<path d="M4 14v-3a8 8 0 0 1 16 0v3"/><rect x="2" y="12" width="5" height="9" rx="2"/><rect x="17" y="12" width="5" height="9" rx="2"/>',

    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v.5"/>',
    "refresh": '<path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
    "remove": '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14M10 11v6m4-6v6"/>',
    "external": '<path d="M14 3h7v7m0-7L10 14M10 5H4v16h16v-6"/>',
    "connect": '<path d="M8 3v5m8-5v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4"/>',
    "disconnect": '<path d="M8 3v4m8-4v4M6 10h12v2a6 6 0 0 1-12 0zM12 18v3M3 3l18 18"/>',
    "share": '<circle cx="6" cy="12" r="3"/><circle cx="18" cy="5" r="3"/><circle cx="18" cy="19" r="3"/><path d="m9 10 6-4m-6 8 6 4"/>',
    "clear": '<path d="m9 4 12 12-5 5H8L2 15zM6 11l10 10M16 21h6"/>',
    "save": '<path d="M4 3h13l4 4v14H3V3zM7 3v6h10V3M7 21v-8h10v8"/>',
}


def line_icon(name: str) -> QIcon:
    icon = QIcon()
    for mode, color in ((QIcon.Mode.Normal, "#dce5f2"), (QIcon.Mode.Disabled, "#718096")):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
               f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" '
               f'stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        for size in (18, 36, 54):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            icon.addPixmap(pixmap, mode)
    return icon


def device_icon_kind(name):
    """Conservative name-based hints; ambiguous HID devices stay generic."""
    import re
    text = name.casefold()
    categories = (
        ("mouse", r"mouse|rat[o?]n|trackball|touchpad"),
        ("keyboard", r"keyboard|teclado|keypad"),
        ("gaming", r"gamepad|joystick|hotas|hosas|gaming|xbox|dualshock|dualsense|thrustmaster|vkb|virpil|flight|rudder"),
        ("camera", r"camera|c[a?]mara|webcam|true vision"),
        ("audio", r"headset|headphone|microphone|micr[o?]fono|audio|speaker"),
        ("network", r"ethernet|gbe|network|bluetooth|wi-?fi|wireless.*adapter"),
    )
    for kind, pattern in categories:
        if re.search(pattern, text):
            return kind
    return "usb"
