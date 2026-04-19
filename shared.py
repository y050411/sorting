import os

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFileDialog, QMenu, QScrollArea, QSizePolicy, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent


TAB_NAMES = [
    "רשימת אמנים",
    "מיון וחיפוש",
    "פיצ'רים נוספים",
    "הגדרות וחוויית משתמש"
]


def app_data_path(filename: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)


def load_stylesheet() -> str:
    """Load the application QSS stylesheet."""
    qss_path = app_data_path("style.qss")
    if os.path.isfile(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


class HebrewLineEdit(QLineEdit):
    def contextMenuEvent(self, event):
        menu = QMenu(self)

        cut_action = menu.addAction("גזור")
        cut_action.triggered.connect(self.cut)
        cut_action.setEnabled(self.hasSelectedText() and not self.isReadOnly())

        copy_action = menu.addAction("העתק")
        copy_action.triggered.connect(self.copy)
        copy_action.setEnabled(self.hasSelectedText())

        paste_action = menu.addAction("הדבק")
        paste_action.triggered.connect(self.paste)
        paste_action.setEnabled(bool(QApplication.clipboard().text()) and not self.isReadOnly())

        delete_action = menu.addAction("מחק")
        delete_action.triggered.connect(self._delete_selected)
        delete_action.setEnabled(self.hasSelectedText() and not self.isReadOnly())

        menu.addSeparator()

        select_all_action = menu.addAction("בחר הכל")
        select_all_action.triggered.connect(self.selectAll)
        select_all_action.setEnabled(len(self.text()) > 0)

        menu.exec(event.globalPos())

    def _delete_selected(self):
        if not self.hasSelectedText():
            return
        start = self.selectionStart()
        length = len(self.selectedText())
        t = self.text()
        self.setText(t[:start] + t[start + length:])
        self.setCursorPosition(start)


class FolderSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.current_folder = ""
        self.setObjectName("folderSelector")
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 10, 12, 10)

        title = QLabel("בחר תיקיית שירים:")
        title.setObjectName("folderTitle")

        self.path_edit = HebrewLineEdit()
        self.path_edit.setReadOnly(False)
        self.path_edit.setPlaceholderText("אפשר להדביק נתיב, או לגרור תיקייה לכאן...")
        self.path_edit.setMinimumWidth(350)
        self.path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.path_edit.setAcceptDrops(True)

        browse_btn = QPushButton("עיון...")
        browse_btn.setObjectName("browseFolderBtn")
        browse_btn.clicked.connect(self.open_dialog)

        self.path_edit.textChanged.connect(self.on_path_changed)

        layout.addWidget(title)
        layout.addWidget(self.path_edit)
        layout.addWidget(browse_btn)

    def open_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "בחר תיקיה")
        if folder:
            self.path_edit.setText(folder)

    def on_path_changed(self, text):
        self.current_folder = text.strip()
        is_valid = (not self.current_folder) or os.path.isdir(self.current_folder)
        self._set_valid_style(is_valid=is_valid)

    def _set_valid_style(self, is_valid: bool):
        self.path_edit.setProperty("cssClass", "invalid" if not is_valid else "")
        self.path_edit.style().unpolish(self.path_edit)
        self.path_edit.style().polish(self.path_edit)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._event_has_local_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent):
        if self._event_has_local_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        try:
            folder = self._extract_folder_from_drop(event)
            if folder:
                self.path_edit.setText(folder)
                event.acceptProposedAction()
            else:
                event.ignore()
        finally:
            self.on_path_changed(self.path_edit.text())

    def _event_has_local_file(self, event) -> bool:
        md = event.mimeData()
        return md is not None and md.hasUrls()

    def _extract_folder_from_drop(self, event) -> str | None:
        md = event.mimeData()
        if md is None or not md.hasUrls():
            return None
        urls = md.urls()
        if not urls:
            return None

        local_path = urls[0].toLocalFile()
        if not local_path:
            return None

        if os.path.isdir(local_path):
            return local_path
        if os.path.isfile(local_path):
            return os.path.dirname(local_path)
        return None


class PlaceholderTab(QWidget):
    def __init__(self, name: str):
        super().__init__()
        layout = QVBoxLayout(self)
        placeholder = QLabel(f"זה המקום של: {name}")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setProperty("cssClass", "pageTitle")
        placeholder.setStyleSheet("padding: 50px; color: #64748b;")
        layout.addWidget(placeholder)
        layout.addStretch()


class ScrollableTab(QWidget):
    def __init__(self, content_widget: QWidget):
        super().__init__()
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content_widget)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(scroll)
