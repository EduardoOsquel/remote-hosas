"""Application credits, separate from future licensing decisions."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout, QLayout
from app_icon import APP_NAME, APP_VERSION, application_icon

CREATOR_NAME = "Eduardo Osquel Pérez Rivero"


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About " + APP_NAME)
        self.setWindowIcon(application_icon())
        self.setMinimumWidth(520)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setSizeGripEnabled(False)
        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        heading = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(application_icon().pixmap(64, 64))
        heading.addWidget(icon)
        title = QLabel(APP_NAME)
        title.setProperty("role", "heading")
        title.setWordWrap(True)
        heading.addWidget(title, 1)
        layout.addLayout(heading)
        layout.addWidget(QLabel("Version " + APP_VERSION))
        description = QLabel("Share USB devices between Windows PCs and monitor local or imported controllers.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.creator_label = QLabel("Created by " + CREATOR_NAME if CREATOR_NAME else "Creator details pending")
        self.creator_label.setTextFormat(Qt.TextFormat.PlainText)
        self.creator_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.creator_label)
        contact = QLabel('<a href="mailto:eduardoosquel@hotmail.com" style="color: #89baff">eduardoosquel@hotmail.com</a><br>'
                         '<a href="https://github.com/EduardoOsquel" style="color: #89baff">github.com/EduardoOsquel</a>')
        contact.setOpenExternalLinks(True)
        layout.addWidget(contact)
        availability = QLabel("Currently provided at no charge. Future versions may have different availability or licensing terms.")
        availability.setWordWrap(True)
        layout.addWidget(availability)
        credits = QLabel("""Built with Python, PyQt6 and pygame.
USB/IP components: usbipd-win and usbip-win2.
Third-party components retain their respective licenses.""")
        credits.setWordWrap(True)
        credits.setProperty("role", "muted")
        layout.addWidget(credits)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setFixedSize(520, max(580, self.sizeHint().height()))
