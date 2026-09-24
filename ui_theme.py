"""Shared visual style and layout defaults for the main application."""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QApplication, QPushButton, QSizePolicy, QVBoxLayout,
                            QStyledItemDelegate, QStyleOptionViewItem, QStyle)

from ui_icons import line_icon


class DeviceStateDelegate(QStyledItemDelegate):
    """Keep semantic state colors readable even on a selected row."""

    COLORS = {"Connected": "#89dcc3", "Shared": "#89dcc3", "Shared (forced)": "#89dcc3", "Attached": "#8bddf2"}

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        option.displayAlignment = Qt.AlignmentFlag.AlignCenter

    def paint(self, painter, option, index):
        color = self.COLORS.get(index.data())
        if color is None:
            super().paint(painter, option, index)
            return
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        text = styled.text
        styled.text = ""
        style = styled.widget.style() if styled.widget else QApplication.style()
        painter.save()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, styled.widget)
        painter.setFont(styled.font)
        painter.setPen(QColor(color))
        rect = styled.rect.adjusted(10, 0, -10, 0)
        painter.setClipRect(styled.rect)
        text = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()


def setup_page(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)


def make_button(text: str, icon: str | None = None) -> QPushButton:
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    if icon:
        button.setIcon(line_icon(icon))
        button.setIconSize(QSize(18, 18))
    return button


APP_STYLESHEET = """
QWidget { background: #101722; color: #dce5f2; font-family: "Segoe UI"; font-size: 10pt; }
QTabWidget::pane { border: 1px solid #29364a; }
QTabBar::tab { padding: 13px 22px; background: #182232; color: #aab9cf; margin-right: 2px; }
QTabBar::tab:selected { background: #22324a; color: #ffffff; border-bottom: 3px solid #63a5ff; }
QTabBar::tab:hover { background: #25364d; }
QLabel { background: transparent; }
QLabel[role="heading"] { font-size: 16pt; font-weight: 600; color: #f0f5fc; }
QLabel[role="muted"] { color: #9aaec8; }
QLabel[role="badge"] { border-radius: 5px; padding: 4px 9px; background: #253247; color: #bfcde0; }
QLabel[role="badge"][detected="true"] { background: #193c36; color: #89dcc3; }
QFrame[role="card"] { background: #141e2c; border: 1px solid #29364a; border-radius: 8px; }
QLabel[role="cardTitle"] { font-size: 12pt; font-weight: 600; }
QProgressBar { border: none; background: #223148; max-height: 3px; }
QProgressBar::chunk { background: #63a5ff; }
QGroupBox { border: 1px solid #29364a; border-radius: 8px; margin-top: 12px; padding: 16px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #aab9cf; }
QComboBox, QLineEdit, QSpinBox { background: #182232; border: 1px solid #384961; border-radius: 6px; padding: 7px 10px; min-height: 20px; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus { border: 1px solid #63a5ff; }
QComboBox QAbstractItemView { background: #182232; selection-background-color: #294c78; selection-color: #ffffff; }
QTextEdit { background: #121c2a; border: 1px solid #29364a; border-radius: 6px; padding: 10px; font-family: "Consolas"; font-size: 9pt; color: #aab9cf; }
QTableWidget { background: #141e2c; alternate-background-color: #192535; border: 1px solid #29364a; selection-background-color: #294c78; selection-color: #ffffff; }
QTableWidget::item { padding: 6px 10px; border-bottom: 1px solid #223044; }
QTableWidget::item:selected { background: #294c78; color: #ffffff; }
QHeaderView::section { background: #202d40; color: #bfcde0; border: none; border-bottom: 1px solid #384961; padding: 10px; font-weight: 600; }
QPushButton { background: #223148; border: 1px solid #405570; border-radius: 6px; padding: 8px 16px; min-height: 20px; font-weight: 600; }
QPushButton:hover { background: #2e4462; border-color: #7097c5; }
QPushButton:pressed { background: #18283d; }
QPushButton:focus { border: 1px solid #8bbcff; }
QPushButton[primary="true"] { background: #326ac5; border-color: #5187dd; color: white; }
QPushButton[primary="true"]:hover { background: #3e79d6; }
QPushButton:disabled { background: #1a2432; color: #718096; border-color: #29364a; }
QComboBox:disabled { color: #8291a6; }
QSplitter::handle { background: #29364a; height: 5px; }
QSplitter::handle:hover { background: #63a5ff; }
QScrollBar:vertical { background: #121c2a; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: #405570; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background: #182232; color: #e6edf7; border: 1px solid #405570; padding: 5px; }
QMenu::item { padding: 8px 28px 8px 14px; border-radius: 4px; }
QMenu::item:selected { background: #326ac5; color: #ffffff; }
QMenu::item:disabled { color: #8291a6; background: transparent; }
QMenu::separator { height: 1px; background: #384961; margin: 5px 8px; }
QToolButton#sectionHeader { background: #202d40; color: #dce5f2; border: 1px solid #384961; border-radius: 5px; padding: 6px 12px; text-align: left; }
QToolButton#sectionHeader:hover { background: #293e59; }
QToolButton#sectionHeader:focus { border-color: #63a5ff; }
QToolTip { background: #223148; color: #ffffff; border: 1px solid #405570; padding: 5px; }
"""
