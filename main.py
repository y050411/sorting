import sys
import os
import json
import time
import uuid
import subprocess
import tempfile
import atexit

from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QTabWidget
from PyQt6.QtCore import Qt

from shared import FolderSelector, ScrollableTab, PlaceholderTab, app_data_path
from artists_tab import ArtistsTab
from sorting_tab import SortingTab
from features_tab import FeaturesTab


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


class MainWindow(QMainWindow):
    def __init__(self, loading_manager: ExternalLoadingManager | None = None):
        super().__init__()
        self._loading_manager = loading_manager
        self.setWindowTitle("מנהל שירים חכם")
        self.setMinimumSize(900, 600)
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
        sorting_tab = SortingTab(artists_tab=artists_tab)
        tabs.addTab(ScrollableTab(sorting_tab), "מיון וחיפוש")

        self._set_loading_status('טוען את הלשונית "פיצ\'רים נוספים"...', 94)
        features_tab = FeaturesTab(artists_tab=artists_tab)
        tabs.addTab(ScrollableTab(features_tab), "פיצ'רים נוספים")

        self._set_loading_status('טוען את הלשונית "הגדרות וחוויית משתמש"...', 97)
        tabs.addTab(ScrollableTab(PlaceholderTab("הגדרות וחוויית משתמש")), "הגדרות וחוויית משתמש")

        main_layout.addWidget(tabs)

        self._set_loading_status("מבצע נגיעות אחרונות...", 98)
        self.setCentralWidget(main_widget)
        self.setStyleSheet("QMainWindow { background: #f6f7f9; }")

        self._set_loading_status("הטעינה הושלמה", 100)


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
