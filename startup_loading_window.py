import sys
import os
import json
import time

from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QWidget, QProgressBar
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush


class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(16)
        self.setFixedSize(78, 78)

    def _rotate(self):
        self._angle = (self._angle + 8) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)
        center = rect.center()

        for i in range(12):
            painter.save()
            painter.translate(center)
            painter.rotate(self._angle - i * 30)

            alpha = max(30, 255 - i * 18)
            color = QColor(255, 224, 130, alpha)

            pen = QPen(color, 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            painter.drawLine(0, -24, 0, -11)
            painter.restore()


class ThinkingBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._offset = 0
        self._direction = 1
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance)
        self._timer.start(16)
        self.setMinimumHeight(18)
        self.setMaximumHeight(18)

    def _advance(self):
        self._offset += self._direction * 5
        max_offset = max(0, self.width() - 110)

        if self._offset >= max_offset:
            self._offset = max_offset
            self._direction = -1
        elif self._offset <= 0:
            self._offset = 0
            self._direction = 1

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30))
        painter.drawRoundedRect(bg_rect, 9, 9)

        chunk_width = min(110, max(50, self.width() // 4))
        x = min(self._offset, max(0, self.width() - chunk_width))
        chunk_rect = QRectF(x, 2, chunk_width, self.height() - 4)

        painter.setBrush(QBrush(QColor(150, 230, 255, 230)))
        painter.drawRoundedRect(chunk_rect, 7, 7)

        shine_rect = QRectF(x + chunk_width * 0.30, 2, chunk_width * 0.25, self.height() - 4)
        painter.setBrush(QBrush(QColor(255, 255, 255, 170)))
        painter.drawRoundedRect(shine_rect, 6, 6)


class StartupLoadingDialog(QDialog):
    def __init__(self, status_file_path: str, ready_file_path: str):
        super().__init__()
        self._status_file_path = status_file_path
        self._ready_file_path = ready_file_path
        self._last_done_seen_at: float | None = None
        self._ready_written = False

        self.setObjectName("loadingDialog")
        self.setWindowTitle("טוען...")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setMinimumSize(640, 360)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        # Load QSS if running standalone
        qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.qss")
        if os.path.isfile(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(22, 22, 22, 22)

        panel = QWidget()
        panel.setObjectName("loadingPanel")
        outer_layout.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(34, 28, 34, 28)
        layout.setSpacing(14)

        self.spinner = LoadingSpinner()

        self.title_label = QLabel("מנהל שירים חכם")
        self.title_label.setObjectName("loadingTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("מפעיל את התוכנה...")
        self.status_label.setObjectName("loadingStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("loadingProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        self.percent_label = QLabel("0%")
        self.percent_label.setObjectName("loadingPercent")
        self.percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.thinking_bar = ThinkingBar()

        layout.addStretch()
        layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.status_label)
        layout.addSpacing(10)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.percent_label)
        layout.addSpacing(10)
        layout.addWidget(self.thinking_bar)
        layout.addStretch()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_status_file)
        self._poll_timer.start(100)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._ready_written:
            self._write_ready_file()

    def _write_ready_file(self):
        self._ready_written = True
        try:
            with open(self._ready_file_path, "w", encoding="utf-8") as f:
                f.write("ready")
        except Exception:
            pass

    def _poll_status_file(self):
        data = self._read_status_file()
        if not data:
            return

        progress = max(0, min(100, int(data.get("progress", 0))))
        status_text = str(data.get("status_text", "טוען..."))
        is_done = bool(data.get("is_done", False))

        self.progress_bar.setValue(progress)
        self.percent_label.setText(f"{progress}%")
        self.status_label.setText(status_text)

        if is_done:
            now = time.time()
            if self._last_done_seen_at is None:
                self._last_done_seen_at = now
            elif now - self._last_done_seen_at >= 0.35:
                self.close()
        else:
            self._last_done_seen_at = None

    def _read_status_file(self):
        if not os.path.exists(self._status_file_path):
            return None
        try:
            with open(self._status_file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


if __name__ == "__main__":
    status_file = sys.argv[1] if len(sys.argv) > 1 else ""
    ready_file = sys.argv[2] if len(sys.argv) > 2 else ""

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    dlg = StartupLoadingDialog(status_file, ready_file)
    dlg.show()
    sys.exit(app.exec())
