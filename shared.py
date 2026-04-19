import os
import sys

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
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)


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

        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("בחר תיקיית שירים:")
        title.setStyleSheet("font-size:17px; font-weight: bold;")

        self.path_edit = HebrewLineEdit()
        self.path_edit.setReadOnly(False)
        self.path_edit.setPlaceholderText("אפשר להדביק נתיב, או לגרור תיקייה לכאן...")
        self.path_edit.setMinimumWidth(350)
        self.path_edit.setStyleSheet("background: #fff; font-size: 16px; padding: 6px;")
        self.path_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.path_edit.setAcceptDrops(True)

        browse_btn = QPushButton("עיון...")
        browse_btn.setStyleSheet("""
            QPushButton {background: #4682b4; color: #fff; border-radius: 8px; padding: 7px 18px; font-size:16px;}
            QPushButton:hover {background: #1e4972;}
        """)
        browse_btn.clicked.connect(self.open_dialog)

        self.path_edit.textChanged.connect(self.on_path_changed)

        layout.addWidget(title)
        layout.addWidget(self.path_edit)
        layout.addWidget(browse_btn)

        self._set_valid_style(is_valid=True)

    def open_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "בחר תיקיה")
        if folder:
            self.path_edit.setText(folder)

    def on_path_changed(self, text):
        self.current_folder = text.strip()
        is_valid = (not self.current_folder) or os.path.isdir(self.current_folder)
        self._set_valid_style(is_valid=is_valid)

    def _set_valid_style(self, is_valid: bool):
        if is_valid:
            self.path_edit.setStyleSheet("background: #fff; font-size: 16px; padding: 6px;")
        else:
            self.path_edit.setStyleSheet("background: #ffe5e5; font-size: 16px; padding: 6px;")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if self._event_has_local_file(event):
            event.acceptProposedAction()
            self.path_edit.setStyleSheet("background: #e8f2ff; font-size: 16px; padding: 6px;")
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
        placeholder.setStyleSheet("font-size: 30px; color: #555; padding: 50px;")
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
