"""Shared device details and compact activity presentation."""
from PyQt6.QtCore import Qt, QEvent, QTimer
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QToolButton, QSizePolicy, QScrollArea, QStyle, QLayout

HOST_STATES = {
    "Not shared": "Not shared - share this device to make it available to a client.",
    "Shared": "Shared - available for a client to connect.",
    "Shared (forced)": "Shared - available for a client (forced binding).",
    "Attached": "Connected to a client - the host reports an active attachment.",
}


def details_label(compact=False):
    label = QLabel("Select a device to see its details.")
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if not compact:
        label.setMinimumHeight(label.fontMetrics().lineSpacing() * 5 + 24)
    label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setStyleSheet("padding: 10px; background: #152130; border: 1px solid #304056; border-radius: 6px;")
    return label


class ActivityPanel(QWidget):
    def __init__(self, editor):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.summary = QLabel("Ready")
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color: #ffb4a9;")
        self.error.hide()
        self.toggle = QToolButton()
        self.toggle.setText("Activity log")
        self.toggle.setObjectName("sectionHeader")
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggle.setMinimumHeight(38)
        self.toggle.setAccessibleName("Expand or collapse activity log")
        self.toggle.setCheckable(True)
        self.toggle.toggled.connect(self.set_expanded)
        self.editor = editor
        editor.setFixedHeight(150)
        editor.hide()
        layout.addWidget(self.summary)
        layout.addWidget(self.error)
        layout.addWidget(self.toggle)
        layout.addWidget(editor)

    def set_expanded(self, expanded):
        self.editor.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle.setToolTip("Collapse activity log" if expanded else "Expand activity log")
        self.layout().invalidate()
        self.updateGeometry()
        parent = self.parentWidget()
        while parent is not None:
            if parent.layout() is not None:
                parent.layout().invalidate()
            if isinstance(parent, ContentScrollArea):
                parent.fit_content()
                break
            parent = parent.parentWidget()

    def update_message(self, message):
        # Both tabs show operation status, never incidental detail lines.
        if message.startswith("> "):
            self.summary.setText("In progress: " + message[2:])
            self.error.clear()
            self.error.hide()
        elif message.startswith("[OK]"):
            self.summary.setText(message)
            self.error.clear()
            self.error.hide()
        elif message.startswith("[ERROR]"):
            self.summary.setText("Operation failed. See details below.")
            self.error.setText(message)
            self.error.show()


class ContentScrollArea(QScrollArea):
    """Size the page from its current layout, not a stale expanded size hint."""
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(False)
        self.setFrameShape(self.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._pending = False
        self._sizing = False

    def setWidget(self, widget):
        super().setWidget(widget)
        widget.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.LayoutRequest:
            self.schedule_fit()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_content()

    def schedule_fit(self):
        if not self._pending:
            self._pending = True
            QTimer.singleShot(0, self.fit_content)

    def fit_content(self):
        self._pending = False
        page = self.widget()
        if self._sizing or page is None or page.layout() is None:
            return
        self._sizing = True
        try:
            layout = page.layout()
            layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            # Reserve the scrollbar gutter even when hidden: disclosure never
            # changes line wrapping or the horizontal position of the controls.
            width = max(1, self.maximumViewportSize().width()
                - self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent))
            layout.invalidate()
            height = layout.totalHeightForWidth(width) if layout.hasHeightForWidth() else layout.sizeHint().height()
            page.resize(width, max(1, height))
            layout.activate()
        finally:
            self._sizing = False
