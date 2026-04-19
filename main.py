import sys
import os
import json
import time
import uuid
import subprocess
import tempfile
import atexit

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QMessageBox, QDialog, QLabel,
    QScrollArea, QFrame, QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from shared import FolderSelector, ScrollableTab, PlaceholderTab, app_data_path
from artists_tab import ArtistsTab
from sorting_tab import SortingTab
from features_tab import FeaturesTab
from undo_manager import UndoManager
from settings_manager import SettingsManager


class ExternalLoadingManager:
    def __init__(self):
        unique_id = uuid.uuid4().hex
        temp_dir = tempfile.gettempdir()

        self._status_file_path = os.path.join(
            temp_dir,
            f"smart_songs_loading_{unique_id}.json"
        )
        self._ready_file_path = os.path.join(
            temp_dir,
            f"smart_songs_loading_{unique_id}.ready"
        )

        self._process: subprocess.Popen | None = None
        self._closed = False

        self._write_status(
            progress=0,
            status_text="מפעיל את התוכנה...",
            is_done=False
        )

        atexit.register(self.close)

    def start(self):
        if self._process is not None:
            return

        self._process = subprocess.Popen(
            [
                sys.executable,
                app_data_path("startup_loading_window.py"),
                self._status_file_path,
                self._ready_file_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def wait_until_ready(self, timeout: float = 2.0, poll_interval: float = 0.02) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.exists(self._ready_file_path):
                return True

            if self._process is not None and self._process.poll() is not None:
                return False

            time.sleep(poll_interval)

        return os.path.exists(self._ready_file_path)

    def update(self, progress: int, status_text: str):
        self._write_status(
            progress=progress,
            status_text=status_text,
            is_done=False
        )

    def finish(self, status_text: str = "הטעינה הושלמה"):
        self._write_status(
            progress=100,
            status_text=status_text,
            is_done=True
        )

    def close(self):
        if self._closed:
            return
        self._closed = True

        try:
            if self._process is not None:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                except Exception:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
        except Exception:
            pass

        for path in (self._status_file_path, self._ready_file_path):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    def _write_status(self, progress: int, status_text: str, is_done: bool):
        data = {
            "progress": max(0, min(100, int(progress))),
            "status_text": str(status_text),
            "is_done": bool(is_done),
            "updated_at": time.time(),
        }

        tmp_path = self._status_file_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._status_file_path)
        except Exception:
            pass


class UndoHistoryDialog(QDialog):
    """Dialog listing all undo-able batches."""

    def __init__(self, undo_manager: UndoManager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("היסטוריית פעולות — ביטול")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumSize(540, 400)
        self._undo_manager = undo_manager
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("פעולות שניתן לבטל")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1c355e;")
        layout.addWidget(title)

        hint = QLabel("לחץ על 'בטל' ליד כל פעולה כדי לבטל אותה, או על 'בטל את האחרונה' לביטול הפעולה האחרונה.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #666;")
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(6)
        scroll.setWidget(self._content)
        layout.addWidget(scroll, 1)

        self._refresh()

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        undo_last_btn = QPushButton("בטל את האחרונה")
        undo_last_btn.setStyleSheet("""
            QPushButton {background: #e74c3c; color: #fff; border-radius: 8px; padding: 8px 20px; font-size:14px; font-weight:700;}
            QPushButton:hover {background: #c0392b;}
            QPushButton:disabled {background: #ccc;}
        """)
        undo_last_btn.setEnabled(self._undo_manager.can_undo)
        undo_last_btn.clicked.connect(self._undo_last)
        bottom.addWidget(undo_last_btn)
        self._undo_last_btn = undo_last_btn

        clear_btn = QPushButton("נקה היסטוריה")
        clear_btn.setStyleSheet("""
            QPushButton {background: #95a5a6; color: #fff; border-radius: 8px; padding: 8px 16px; font-size:13px; font-weight:600;}
            QPushButton:hover {background: #7f8c8d;}
        """)
        clear_btn.clicked.connect(self._clear_all)
        bottom.addWidget(clear_btn)

        bottom.addStretch()

        close_btn = QPushButton("סגור")
        close_btn.setStyleSheet("""
            QPushButton {background: #3498db; color: #fff; border-radius: 8px; padding: 8px 20px; font-size:14px; font-weight:700;}
            QPushButton:hover {background: #2980b9;}
        """)
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _refresh(self):
        # Clear existing
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        batches = self._undo_manager.batches
        if not batches:
            empty_lbl = QLabel("אין פעולות לביטול")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet("font-size: 16px; color: #999; padding: 30px;")
            self._content_layout.addWidget(empty_lbl)
            self._content_layout.addStretch()
            return

        import datetime
        for batch in reversed(batches):
            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: #f7faff;
                    border: 1px solid #dce6f0;
                    border-radius: 8px;
                    padding: 6px;
                }
            """)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 6, 10, 6)
            rl.setSpacing(10)

            ts = datetime.datetime.fromtimestamp(batch.timestamp).strftime("%H:%M:%S  %d/%m/%Y")
            info = QLabel(f"<b>{batch.description}</b><br><small>{ts} · {len(batch.actions)} פעולות</small>")
            info.setStyleSheet("font-size: 13px; color: #1e293b; background: transparent; border: none;")
            info.setWordWrap(True)
            rl.addWidget(info, 1)

            undo_btn = QPushButton("בטל")
            undo_btn.setStyleSheet("""
                QPushButton {background: #e67e22; color: #fff; border-radius: 6px; padding: 5px 14px; font-size:13px; font-weight:700;}
                QPushButton:hover {background: #d35400;}
            """)
            bid = batch.batch_id
            undo_btn.clicked.connect(lambda _, b=bid: self._undo_by_id(b))
            rl.addWidget(undo_btn)

            self._content_layout.addWidget(row)

        self._content_layout.addStretch()

    def _undo_last(self):
        ok, msg = self._undo_manager.undo_last()
        if ok:
            QMessageBox.information(self, "ביטול פעולה", msg)
        else:
            QMessageBox.warning(self, "ביטול פעולה", msg)
        self._refresh()
        self._undo_last_btn.setEnabled(self._undo_manager.can_undo)

    def _undo_by_id(self, batch_id: str):
        ok, msg = self._undo_manager.undo_batch_by_id(batch_id)
        if ok:
            QMessageBox.information(self, "ביטול פעולה", msg)
        else:
            QMessageBox.warning(self, "ביטול פעולה", msg)
        self._refresh()
        self._undo_last_btn.setEnabled(self._undo_manager.can_undo)

    def _clear_all(self):
        reply = QMessageBox.question(
            self, "נקה היסטוריה",
            "למחוק את כל היסטוריית הפעולות?\nפעולה זו בלתי הפיכה.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._undo_manager.clear_all()
            self._refresh()
            self._undo_last_btn.setEnabled(False)


class MainWindow(QMainWindow):
    def __init__(self, loading_manager: ExternalLoadingManager | None = None):
        super().__init__()
        self._loading_manager = loading_manager
        self.setWindowTitle("מנהל שירים חכם")
        self.setMinimumSize(900, 600)

        # Shared managers
        self.undo_manager = UndoManager()
        self.settings_manager = SettingsManager()

        self.setup_ui()

    def _set_loading_status(self, text: str, value: int):
        if self._loading_manager is not None:
            self._loading_manager.update(value, text)

    def _update_stage_progress(self, stage_start: int, stage_end: int, current: int, total: int, text: str):
        total = max(1, total)
        current = max(0, min(current, total))
        ratio = current / total
        value = round(stage_start + (stage_end - stage_start) * ratio)
        self._set_loading_status(text, value)

    def setup_ui(self):
        self._set_loading_status("בונה את חלון התוכנה...", 3)

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(18)
        main_layout.setContentsMargins(15, 15, 15, 15)

        self._set_loading_status("טוען רכיבי בחירת תיקייה...", 12)
        self.folder_selector = FolderSelector()
        main_layout.addWidget(self.folder_selector)
        self._set_loading_status("רכיבי בחירת תיקייה נטענו", 25)

        self._set_loading_status("מכין את הלשוניות הראשיות...", 32)
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 0; background: #f8f8fc; }
            QTabBar::tab:selected { background: #a7cdf7; color: #1c355e; font-weight: bold; }
            QTabBar::tab { background: #daeaff; min-width:150px; min-height: 38px; font-size:17px; margin:2px; padding: 4px 10px; }
        """)
        tabs.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # ── Buttons next to the tabs ──
        corner_widget = QWidget()
        corner_layout = QHBoxLayout(corner_widget)
        corner_layout.setContentsMargins(4, 2, 4, 2)
        corner_layout.setSpacing(6)

        self.undo_btn = QPushButton("↩ ביטול פעולות")
        self.undo_btn.setToolTip("הצג את היסטוריית הפעולות ובטל פעולות שבוצעו")
        self.undo_btn.setStyleSheet("""
            QPushButton {
                background: #e74c3c; color: #fff; border-radius: 8px;
                padding: 5px 14px; font-size: 13px; font-weight: 800;
            }
            QPushButton:hover { background: #c0392b; }
            QPushButton:disabled { background: #ccc; color: #888; }
        """)
        self.undo_btn.clicked.connect(self._open_undo_dialog)
        corner_layout.addWidget(self.undo_btn)

        self.save_settings_btn = QPushButton("💾 שמור הגדרות")
        self.save_settings_btn.setToolTip("שמור את כל הבחירות הנוכחיות כברירת מחדל לפעם הבאה")
        self.save_settings_btn.setStyleSheet("""
            QPushButton {
                background: #27ae60; color: #fff; border-radius: 8px;
                padding: 5px 14px; font-size: 13px; font-weight: 800;
            }
            QPushButton:hover { background: #1e8449; }
        """)
        self.save_settings_btn.clicked.connect(self._save_settings)
        corner_layout.addWidget(self.save_settings_btn)

        self.reset_settings_btn = QPushButton("🔄 איפוס הגדרות")
        self.reset_settings_btn.setToolTip("מחק את כל ההגדרות השמורות וחזור לברירות המחדל")
        self.reset_settings_btn.setStyleSheet("""
            QPushButton {
                background: #e67e22; color: #fff; border-radius: 8px;
                padding: 5px 14px; font-size: 13px; font-weight: 800;
            }
            QPushButton:hover { background: #d35400; }
        """)
        self.reset_settings_btn.clicked.connect(self._reset_settings)
        corner_layout.addWidget(self.reset_settings_btn)

        tabs.setCornerWidget(corner_widget, Qt.Corner.TopRightCorner)

        self._set_loading_status("מבנה הלשוניות הוכן", 45)

        def artists_progress(current, total):
            self._update_stage_progress(
                stage_start=46,
                stage_end=84,
                current=current,
                total=total,
                text="טוען את רשימת האמנים והנתונים השמורים..."
            )

        artists_tab = ArtistsTab(loading_progress_callback=artists_progress)
        tabs.addTab(ScrollableTab(artists_tab), "רשימת אמנים")

        self._set_loading_status('טוען את הלשונית "מיון וחיפוש"...', 88)
        self.sorting_tab = SortingTab(artists_tab=artists_tab, undo_manager=self.undo_manager)
        tabs.addTab(ScrollableTab(self.sorting_tab), "מיון וחיפוש")

        self._set_loading_status('טוען את הלשונית "פיצ\'רים נוספים"...', 94)
        self.features_tab = FeaturesTab(artists_tab=artists_tab, undo_manager=self.undo_manager)
        tabs.addTab(ScrollableTab(self.features_tab), "פיצ'רים נוספים")

        self._set_loading_status('טוען את הלשונית "הגדרות וחוויית משתמש"...', 97)
        tabs.addTab(ScrollableTab(PlaceholderTab("הגדרות וחוויית משתמש")), "הגדרות וחוויית משתמש")

        main_layout.addWidget(tabs)

        self._set_loading_status("מבצע נגיעות אחרונות...", 98)
        self.setCentralWidget(main_widget)
        self.setStyleSheet("QMainWindow { background: #f6f7f9; }")

        # Apply saved settings if any
        self._apply_saved_settings()

        self._set_loading_status("הטעינה הושלמה", 100)

    # ── Undo dialog ────────────────────────────────────────────────────
    def _open_undo_dialog(self):
        dlg = UndoHistoryDialog(self.undo_manager, parent=self)
        dlg.exec()

    # ── Save settings ──────────────────────────────────────────────────
    def _save_settings(self):
        sm = self.settings_manager
        sm.collect_sorting_tab(self.sorting_tab)
        sm.collect_features_tab(self.features_tab)
        sm.set("general.folder", self.folder_selector.path_edit.text())
        sm.save()
        QMessageBox.information(
            self, "שמירת הגדרות",
            "ההגדרות נשמרו בהצלחה!\n"
            "בפעם הבאה שתפתח את התוכנה, הבחירות שלך יופעלו אוטומטית.",
        )

    # ── Reset settings ─────────────────────────────────────────────────
    def _reset_settings(self):
        reply = QMessageBox.question(
            self, "איפוס הגדרות",
            "האם אתה בטוח שברצונך לאפס את כל ההגדרות השמורות?\n"
            "בפעם הבאה שתפתח את התוכנה, לא ייטענו הגדרות שמורות.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.settings_manager.clear()
            QMessageBox.information(
                self, "איפוס הגדרות",
                "ההגדרות אופסו בהצלחה!\n"
                "בפעם הבאה שתפתח את התוכנה, לא ייטענו הגדרות שמורות.",
            )

    def _apply_saved_settings(self):
        sm = self.settings_manager
        if not sm.has_saved_settings():
            return
        sm.apply_sorting_tab(self.sorting_tab)
        sm.apply_features_tab(self.features_tab)
        v = sm.get("general.folder", "")
        if v:
            self.folder_selector.path_edit.setText(v)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    loading_manager = ExternalLoadingManager()
    loading_manager.start()
    loading_manager.update(5, "מפעיל את התוכנה...")
    loading_manager.wait_until_ready(timeout=2.0)

    window = MainWindow(loading_manager=loading_manager)
    window.show()

    loading_manager.finish("הטעינה הושלמה")

    exit_code = app.exec()

    loading_manager.close()
    sys.exit(exit_code)
