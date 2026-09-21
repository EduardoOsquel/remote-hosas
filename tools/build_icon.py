"""Regenerate PNG and multi-resolution Windows ICO from our original SVG.

Run with the project's Python interpreter; only PyQt6 is required.
"""

import os
from pathlib import Path
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


def main():
    application = QGuiApplication.instance() or QGuiApplication([])
    assets = Path(__file__).resolve().parents[1] / "assets"
    renderer = QSvgRenderer(str(assets / "remote-hosas.svg"))
    if not renderer.isValid():
        raise ValueError("Invalid icon SVG")
    sizes = (16, 24, 32, 48, 64, 128, 256)
    images = []
    for size in (*sizes, 512):
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        if size == 512:
            if not image.save(str(assets / "remote-hosas.png")):
                raise OSError("Could not write PNG")
            continue
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise OSError("Could not encode icon image")
        images.append(bytes(data))
    # ICO directory followed by lossless PNG entries; 0 denotes 256 pixels.
    offset = 6 + 16 * len(sizes)
    directory = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    for size, data in zip(sizes, images):
        directory.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0,
                                     1, 32, len(data), offset))
        offset += len(data)
    (assets / "remote-hosas.ico").write_bytes(directory + b"".join(images))


if __name__ == "__main__":
    main()
