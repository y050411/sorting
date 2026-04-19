import os
import re
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QFrame,
    QGraphicsOpacityEffect,
    QSizePolicy,
    QStackedWidget,
    QProgressDialog,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QInputDialog,
    QComboBox,
)
from PyQt6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    pyqtProperty,
    pyqtSignal,
    QSize,
)
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

from shared import HebrewLineEdit


# ─── Animated check indicator (v-mark) ───
class AnimatedStepIndicator(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(22, 22)
        self._progress = 0.0
        self._checked = False

        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def getProgress(self):
        return self._progress

    def setProgress(self, value):
        value = float(value)
        if abs(self._progress - value) < 0.001:
            return
        self._progress = value
        self.update()

    progress = pyqtProperty(float, fget=getProgress, fset=setProgress)

    def set_checked_animated(self, checked: bool):
        if self._checked == checked:
            return
        self._checked = checked
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, event):
        painter = QPainter()
        if not painter.begin(self):
            return
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = self.rect().adjusted(3, 3, -3, -3)
            center = rect.center()

            # background circle
            base_color = QColor("#e2e8f0")
            painter.setPen(QPen(base_color, 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)

            if self._progress > 0:
                green = QColor("#22c55e")

                # arc
                arc_pen = QPen(green, 2.0)
                arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(arc_pen)
                span = int(360 * 16 * self._progress)
                painter.drawArc(rect, 90 * 16, -span)

                # check mark when complete
                if self._progress >= 0.95:
                    painter.setPen(QPen(green, 1.6))
                    painter.drawEllipse(rect)

                    check_pen = QPen(green, 2.0)
                    check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(check_pen)

                    x1 = center.x() - 3
                    y1 = center.y() + 1
                    x2 = center.x() - 1
                    y2 = center.y() + 3
                    x3 = center.x() + 4
                    y3 = center.y() - 3

                    painter.drawLine(x1, y1, x2, y2)
                    painter.drawLine(x2, y2, x3, y3)
        finally:
            painter.end()


# ─── Compact option button ───
class OptionBtn(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setProperty("cssClass", "optionBtn")

    def setChecked(self, v):
        super().setChecked(v)


# ─── Step row with label + indicator + option buttons ───
class StepRow(QWidget):
    def __init__(self, label: str, options: list[str]):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.indicator = AnimatedStepIndicator()
        row.addWidget(self.indicator, 0, Qt.AlignmentFlag.AlignVCenter)

        lbl = QLabel(label)
        lbl.setFixedWidth(120)
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lbl.setProperty("cssClass", "stepLabel")
        row.addWidget(lbl)

        self.opts: list[OptionBtn] = []
        for txt in options:
            o = OptionBtn(txt)
            self.opts.append(o)
            row.addWidget(o)

        for i, o in enumerate(self.opts):
            o.clicked.connect(lambda _, idx=i: self._select(idx))

    def _select(self, idx):
        for i, o in enumerate(self.opts):
            o.setChecked(i == idx)

    def selected_index(self) -> int:
        for i, o in enumerate(self.opts):
            if o.isChecked():
                return i
        return -1

    def has_selection(self) -> bool:
        return self.selected_index() >= 0

    def set_completed(self, completed: bool):
        self.indicator.set_checked_animated(completed)


# ─── Scanned artist row ───
class ScannedArtistRow(QWidget):
    removeRequested = pyqtSignal(str)
    restoreRequested = pyqtSignal(str)

    def __init__(self, artist_name: str, songs: list[str], is_excluded: bool = False):
        super().__init__()
        self.artist_name = artist_name
        self.songs = songs
        self._expanded = False
        self._is_excluded = is_excluded

        self.setObjectName("scannedArtistRowExcluded" if is_excluded else "scannedArtistRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(3)

        # top row
        top = QHBoxLayout()
        top.setSpacing(6)
        top.setContentsMargins(0, 0, 0, 0)

        if not is_excluded:
            self.expand_btn = QPushButton("◀")
            self.expand_btn.setFixedSize(22, 22)
            self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.expand_btn.setProperty("cssClass", "expandBtn")
            self.expand_btn.clicked.connect(self._toggle_expand)
            top.addWidget(self.expand_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.name_label = QLabel(artist_name)
        name_color = "#92400e" if is_excluded else "#1e293b"
        self.name_label.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {name_color}; background: transparent; border: none;")

        self.count_label = QLabel(f"({len(songs)} שירים)")
        self.count_label.setProperty("cssClass", "hint")

        if is_excluded:
            self.action_btn = QPushButton("החזר למיון")
            self.action_btn.setProperty("cssClass", "restoreToSort")
            self.action_btn.clicked.connect(lambda: self.restoreRequested.emit(self.artist_name))
        else:
            self.action_btn = QPushButton("הסר מהמיון")
            self.action_btn.setProperty("cssClass", "removeFromSort")
            self.action_btn.clicked.connect(lambda: self.removeRequested.emit(self.artist_name))

        self.action_btn.setFixedHeight(24)
        self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        top.addWidget(self.name_label, 1, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(top)

        # songs list (hidden)
        self.songs_widget = QWidget()
        self.songs_widget.setObjectName("songsContainer")
        songs_layout = QVBoxLayout(self.songs_widget)
        songs_layout.setContentsMargins(10, 4, 6, 4)
        songs_layout.setSpacing(1)

        for song_path in songs:
            song_name = os.path.splitext(os.path.basename(song_path))[0]
            song_label = QLabel(f"♪  {song_name}")
            song_label.setProperty("cssClass", "hint")
            song_label.setToolTip(song_path)
            songs_layout.addWidget(song_label)

        self.songs_widget.hide()
        root.addWidget(self.songs_widget)

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self.songs_widget.setVisible(self._expanded)
        self.expand_btn.setText("▼" if self._expanded else "◀")

        from PyQt6.QtWidgets import QListWidget
        self.adjustSize()
        qlist = self.parent()
        while qlist and not isinstance(qlist, QListWidget):
            qlist = qlist.parent()
        if isinstance(qlist, QListWidget):
            for i in range(qlist.count()):
                if qlist.itemWidget(qlist.item(i)) is self:
                    new_height = self.sizeHint().height() + 8
                    qlist.item(i).setSizeHint(QSize(0, new_height))
                    break
# ═══════════════════════════════════════════════
#  Unrecognized-file row (with per-song assign button)
# ═══════════════════════════════════════════════
class UnrecognizedFileRow(QWidget):
    """שורה לשיר לא מזוהה עם כפתור הקצאת אמן ייעודי."""
    assignRequested = pyqtSignal(str)

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath
        self.setObjectName("unrecFileRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(6)

        song_name = os.path.splitext(os.path.basename(filepath))[0]
        lbl = QLabel(f"♪  {song_name}")
        lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #4c1d95; background: transparent; border: none;")
        lbl.setToolTip(filepath)

        btn = QPushButton("הקצה אמן")
        btn.setFixedHeight(24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("cssClass", "assignBtn")
        btn.clicked.connect(lambda: self.assignRequested.emit(self.filepath))

        row.addWidget(lbl, 1, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)


# ═══════════════════════════════════════════════
#  Multi-artist chooser dialog
# ═══════════════════════════════════════════════
class MultiArtistChooserDialog(QDialog):
    def __init__(self, filename: str, artists: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("בחר אמנים")
        self.setMinimumWidth(340)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("<b>הקובץ שייך לכמה אמנים:</b>")
        title.setProperty("cssClass", "sectionTitle")
        layout.addWidget(title)

        fname_label = QLabel(f"📄  {filename}")
        fname_label.setProperty("cssClass", "hint")
        fname_label.setWordWrap(True)
        layout.addWidget(fname_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("cssClass", "separator")
        layout.addWidget(sep)

        self._checkboxes: list[tuple[str, QCheckBox]] = []
        for artist in artists:
            cb = QCheckBox(artist)
            cb.setChecked(True)
            self._checkboxes.append((artist, cb))
            layout.addWidget(cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("אישור")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("דלג")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_artists(self) -> list[str]:
        return [artist for artist, cb in self._checkboxes if cb.isChecked()]


# ═══════════════════════════════════════════════
#  Dialog for assigning artist to unrecognized song
# ═══════════════════════════════════════════════
class AssignArtistDialog(QDialog):
    def __init__(self, filename: str, existing_artists: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("הקצאת אמן לשיר")
        self.setMinimumWidth(380)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("<b>הקצה אמן לשיר לא מזוהה:</b>")
        title.setProperty("cssClass", "labelBold")
        layout.addWidget(title)

        fname_label = QLabel(f"📄  {filename}")
        fname_label.setProperty("cssClass", "hint")
        fname_label.setWordWrap(True)
        layout.addWidget(fname_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("cssClass", "separator")
        layout.addWidget(sep)

        lbl = QLabel("בחר אמן מהרשימה או הקלד שם חדש:")
        lbl.setProperty("cssClass", "labelSmall")
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._combo.addItem("")
        for a in sorted(existing_artists):
            self._combo.addItem(a)
        layout.addWidget(self._combo)

        hint = QLabel("💡 אם תקליד שם שאינו ברשימה, הוא יתווסף כאמן חדש.")
        hint.setProperty("cssClass", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("אישור")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("דלג")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_artist_name(self) -> str:
        return self._combo.currentText().strip()


# ═══════════════════════════════════════════════
#  Dialog for handling album without common artist
# ═══════════════════════════════════════════════
class AlbumNoCommonArtistDialog(QDialog):
    def __init__(self, album_name: str, songs: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("אלבום ללא אמן משותף")
        self.setMinimumWidth(420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel(f"<b>האלבום \"{album_name}\" — אין אמן משותף לכל השירים</b>")
        title.setProperty("cssClass", "labelBold")
        title.setWordWrap(True)
        layout.addWidget(title)

        songs_lbl = QLabel(f"הגדר מה לעשות עם {len(songs)} שיר/ים באלבום זה:")
        songs_lbl.setProperty("cssClass", "labelSmall")
        layout.addWidget(songs_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setProperty("cssClass", "separator")
        layout.addWidget(sep)

        self._choice = "sort_artists"  # default

        btn_sort = QPushButton("מיין כל שיר לתיקיית האמן שלו")
        btn_sort.setProperty("cssClass", "primary")

        btn_folder = QPushButton("הכנס את כל האלבום לתיקייה מסוימת...")
        btn_folder.setProperty("cssClass", "success")

        btn_skip = QPushButton("השאר במקום (אל תבצע שינוי)")
        btn_skip.setProperty("cssClass", "warning")

        self._folder_choice: str | None = None

        def choose_sort():
            self._choice = "sort_artists"
            self.accept()

        def choose_folder():
            folder = QFileDialog.getExistingDirectory(self, "בחר תיקייה לאלבום")
            if folder:
                self._folder_choice = folder
                self._choice = "single_folder"
                self.accept()

        def choose_skip():
            self._choice = "skip"
            self.accept()

        btn_sort.clicked.connect(choose_sort)
        btn_folder.clicked.connect(choose_folder)
        btn_skip.clicked.connect(choose_skip)

        layout.addWidget(btn_sort)
        layout.addWidget(btn_folder)
        layout.addWidget(btn_skip)

    def get_choice(self) -> tuple[str, str | None]:
        """Returns (choice, folder_path). choice is 'sort_artists', 'single_folder', or 'skip'."""
        return self._choice, self._folder_choice


# ═══════════════════════════════════════════════
#  SortingTab — main widget
# ═══════════════════════════════════════════════
class SortingTab(QWidget):
    AUDIO_EXTENSIONS = {
        ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".aiff", ".aif"
    }
    VIDEO_EXTENSIONS = {
        ".mp4", ".avi", ".mkv", ".webm", ".mov", ".wmv"
    }
    # Combined set kept for backward compatibility
    SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

    def __init__(self, artists_tab, undo_manager=None):
        super().__init__()
        self.setFont(QFont("Assistant", 10))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.artists_tab = artists_tab
        self._undo_manager = undo_manager
        self._scanned_artist_names: list[str] = []
        self._sort_mode_selected: str | None = None
        self._animated_sections: list[QWidget] = []
        self._entry_anim_refs = []
        self._target_last_content_height = 170
        self._scan_results: dict[str, list[str]] = {}
        self._excluded_artists: dict[str, list[str]] = {}
        self._unrecognized_files: list[str] = []

        self._build_ui()
        self._connect_signals()
        self._update_step_completion()
        self._update_summary_text()

    # ─── message boxes ───
    def _show_message_box(self, icon, title: str, text: str):
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(f"<div style='font-size:14px;font-weight:800;color:#1e293b;'>{text}</div>")
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()

    def _show_warning(self, text: str):
        self._show_message_box(QMessageBox.Icon.Warning, "שגיאה", text)

    def _show_info(self, title: str, text: str):
        self._show_message_box(QMessageBox.Icon.Information, title, text)

    # ─── main UI build ───
    def _build_ui(self):
        self.setObjectName("sortingTabBase")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(0)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.stack.addWidget(self._build_settings_page())
        self.stack.addWidget(self._build_results_page())

    # ── PAGE 1: Settings ──
    def _build_settings_page(self):
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        # header
        tl = QVBoxLayout(); tl.setSpacing(1)
        title = QLabel("מיון שירים")
        title.setProperty("cssClass", "pageTitle")
        subtitle = QLabel("הגדר את אפשרויות המיון ולחץ המשך לסריקה")
        subtitle.setProperty("cssClass", "pageSubtitle")
        tl.addWidget(title); tl.addWidget(subtitle)
        col.addLayout(tl)

        # settings card
        card = QFrame(); card.setObjectName("settingsCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(14)

        self.step_sort_type = StepRow("סוג מיון:", ["בתיקיית מקור", "לתיקיית יעד"])
        self.step_copy_move = StepRow("פעולה:", ["העתקה", "העברה"])
        self.step_artist_mode = StepRow("זיהוי אמנים:", ["רשימת אמנים", "תיקיות קיימות", "Metadata"])
        self.step_album = StepRow("אלבומים:", ["בתיקיית האמן", "ללא טיפול מיוחד", "תיקייה ייעודית"])
        self.step_multi = StepRow("ריבוי אמנים:", ["לכל האמנים", "רק לראשון", "שאל בכל פעם"])
        self.step_file_types = StepRow("סוג קבצים:", ["רק שירים", "שירים + וידאו"])
        self.step_subfolders = StepRow("תתי תיקיות:", ["כולל תתי תיקיות", "רק תיקיית מקור"])

        cl.addWidget(self.step_sort_type)

        # target folder row (hidden by default)
        self.target_row = QWidget()
        tr_layout = QHBoxLayout(self.target_row)
        tr_layout.setContentsMargins(0, 0, 0, 0)
        tr_layout.setSpacing(8)

        self.target_indicator = AnimatedStepIndicator()
        tr_layout.addWidget(self.target_indicator, 0, Qt.AlignmentFlag.AlignVCenter)

        target_lbl = QLabel("תיקיית יעד:")
        target_lbl.setFixedWidth(120)
        target_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        target_lbl.setProperty("cssClass", "stepLabel")
        tr_layout.addWidget(target_lbl)

        self.target_folder_edit = HebrewLineEdit()
        self.target_folder_edit.setPlaceholderText("בחר תיקיית יעד...")
        self.target_folder_edit.setFixedHeight(32)

        self.target_browse_btn = QPushButton("עיון...")
        self.target_browse_btn.setFixedHeight(32)
        self.target_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.target_browse_btn.setProperty("cssClass", "browse")

        tr_layout.addWidget(self.target_folder_edit, 1)
        tr_layout.addWidget(self.target_browse_btn, 0)

        # target animation setup
        self.target_opacity = QGraphicsOpacityEffect(self.target_row)
        self.target_row.setGraphicsEffect(self.target_opacity)
        self.target_opacity.setOpacity(0.0)
        self.target_row.setMaximumHeight(0)
        self.target_row.hide()

        self.target_height_anim = QPropertyAnimation(self.target_row, b"maximumHeight", self)
        self.target_height_anim.setDuration(250)
        self.target_height_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.target_fade_anim = QPropertyAnimation(self.target_opacity, b"opacity", self)
        self.target_fade_anim.setDuration(200)
        self.target_fade_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.target_anim_group = QParallelAnimationGroup(self)
        self.target_anim_group.addAnimation(self.target_height_anim)
        self.target_anim_group.addAnimation(self.target_fade_anim)
        self.target_anim_group.finished.connect(self._on_target_anim_finished)

        cl.addWidget(self.target_row)

        cl.addWidget(self.step_copy_move)
        cl.addWidget(self.step_artist_mode)
        cl.addWidget(self.step_album)

        # albums dedicated folder row (hidden by default, shown when "תיקייה ייעודית" is selected)
        self.albums_folder_row = QWidget()
        af_layout = QHBoxLayout(self.albums_folder_row)
        af_layout.setContentsMargins(0, 0, 0, 0)
        af_layout.setSpacing(8)

        self.albums_folder_indicator = AnimatedStepIndicator()
        af_layout.addWidget(self.albums_folder_indicator, 0, Qt.AlignmentFlag.AlignVCenter)

        albums_folder_lbl = QLabel("תיקיית אלבומים:")
        albums_folder_lbl.setFixedWidth(120)
        albums_folder_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        albums_folder_lbl.setProperty("cssClass", "stepLabel")
        af_layout.addWidget(albums_folder_lbl)

        self.albums_folder_edit = HebrewLineEdit()
        self.albums_folder_edit.setPlaceholderText("בחר תיקיית אלבומים ייעודית...")
        self.albums_folder_edit.setFixedHeight(32)

        self.albums_folder_browse_btn = QPushButton("עיון...")
        self.albums_folder_browse_btn.setFixedHeight(32)
        self.albums_folder_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.albums_folder_browse_btn.setProperty("cssClass", "browse")

        af_layout.addWidget(self.albums_folder_edit, 1)
        af_layout.addWidget(self.albums_folder_browse_btn, 0)

        # albums folder animation setup
        self.albums_folder_opacity = QGraphicsOpacityEffect(self.albums_folder_row)
        self.albums_folder_row.setGraphicsEffect(self.albums_folder_opacity)
        self.albums_folder_opacity.setOpacity(0.0)
        self.albums_folder_row.setMaximumHeight(0)
        self.albums_folder_row.hide()

        self.albums_folder_height_anim = QPropertyAnimation(self.albums_folder_row, b"maximumHeight", self)
        self.albums_folder_height_anim.setDuration(250)
        self.albums_folder_height_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.albums_folder_fade_anim = QPropertyAnimation(self.albums_folder_opacity, b"opacity", self)
        self.albums_folder_fade_anim.setDuration(200)
        self.albums_folder_fade_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.albums_folder_anim_group = QParallelAnimationGroup(self)
        self.albums_folder_anim_group.addAnimation(self.albums_folder_height_anim)
        self.albums_folder_anim_group.addAnimation(self.albums_folder_fade_anim)
        self.albums_folder_anim_group.finished.connect(self._on_albums_folder_anim_finished)

        cl.addWidget(self.albums_folder_row)

        cl.addWidget(self.step_multi)
        cl.addWidget(self.step_file_types)
        cl.addWidget(self.step_subfolders)

        # divider + summary
        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setProperty("cssClass", "separator")
        cl.addWidget(div)

        self.summary_label = QLabel("בחר את כל ההגדרות כדי להמשיך")
        self.summary_label.setWordWrap(True)
        self.summary_label.setObjectName("summaryLabel")
        cl.addWidget(self.summary_label)

        col.addWidget(card)
        col.addStretch()

        # continue button at bottom
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 6, 0, 0)

        self.continue_btn = QPushButton("המשך לסריקה →")
        self.continue_btn.setFixedHeight(42)
        self.continue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_btn.setObjectName("continueBtn")

        btn_row.addStretch()
        btn_row.addWidget(self.continue_btn)
        btn_row.addStretch()
        col.addLayout(btn_row)

        return page
    # ── PAGE 2: Results ──
    def _build_results_page(self):
        page = QWidget()
        col = QVBoxLayout(page)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)

        # header
        h = QHBoxLayout(); h.setSpacing(8)
        t = QLabel("תוצאות סריקה")
        t.setProperty("cssClass", "pageTitle")

        self.back_btn = QPushButton("← חזרה להגדרות")
        self.back_btn.setFixedHeight(34)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setObjectName("backBtn")

        self.scan_btn = QPushButton("סרוק שוב")
        self.scan_btn.setFixedHeight(34)
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.setObjectName("scanBtn")

        self.sort_btn = QPushButton("▶  מיין עכשיו")
        self.sort_btn.setFixedHeight(34)
        self.sort_btn.setEnabled(True)
        self.sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sort_btn.setObjectName("sortBtn")

        h.addWidget(t, 1)
        h.addWidget(self.back_btn)
        h.addWidget(self.sort_btn)
        h.addWidget(self.scan_btn)
        col.addLayout(h)

        # status bar
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("statusLabel")
        col.addWidget(self.status_label)

        # body — two columns
        body = QHBoxLayout(); body.setSpacing(10)

        # ── included panel ──
        inc = QFrame(); inc.setObjectName("incPanel")
        il = QVBoxLayout(inc); il.setContentsMargins(10, 8, 10, 8); il.setSpacing(6)

        ih = QHBoxLayout(); ih.setSpacing(8)
        it = QLabel("אמנים שימוינו")
        it.setObjectName("incTitle")
        self.result_count_label = QLabel("0 אמנים")
        self.result_count_label.setProperty("cssClass", "badgeBlue")
        ih.addWidget(self.result_count_label, 0)
        ih.addWidget(it, 1)
        il.addLayout(ih)

        self.empty_results_label = QLabel("לחץ 'סרוק שוב' כדי להתחיל")
        self.empty_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_results_label.setWordWrap(True)
        self.empty_results_label.setObjectName("emptyResults")
        il.addWidget(self.empty_results_label)

        self.scanned_artists_list = QListWidget()
        self.results_opacity = QGraphicsOpacityEffect(self.scanned_artists_list)
        self.scanned_artists_list.setGraphicsEffect(self.results_opacity)
        self.results_opacity.setOpacity(1.0)
        il.addWidget(self.scanned_artists_list, 1)

        # ── excluded panel ──
        exc = QFrame(); exc.setObjectName("excPanel")
        el = QVBoxLayout(exc); el.setContentsMargins(10, 8, 10, 8); el.setSpacing(6)

        eh = QHBoxLayout(); eh.setSpacing(8)
        self.excluded_title = QLabel("לא ימוינו")
        self.excluded_title.setObjectName("excTitle")
        self.excluded_count_label = QLabel("0 אמנים")
        self.excluded_count_label.setProperty("cssClass", "badgeAmber")
        eh.addWidget(self.excluded_count_label, 0)
        eh.addWidget(self.excluded_title, 1)
        el.addLayout(eh)

        self.excluded_artists_list = QListWidget()
        self.excluded_artists_list.setObjectName("excludedList")
        el.addWidget(self.excluded_artists_list, 1)

        self.exc_panel = exc

        body.addWidget(inc, 3)
        body.addWidget(exc, 2)
        col.addLayout(body, 1)

        # ── unrecognized files panel ──
        self.unrec_panel = QFrame()
        self.unrec_panel.setObjectName("unrecPanel")
        url = QVBoxLayout(self.unrec_panel)
        url.setContentsMargins(10, 8, 10, 8)
        url.setSpacing(6)

        urh = QHBoxLayout(); urh.setSpacing(8)
        self.unrec_title = QLabel("שירים לא מזוהים")
        self.unrec_title.setObjectName("unrecTitle")
        self.unrec_count_label = QLabel("0 שירים")
        self.unrec_count_label.setProperty("cssClass", "badgePurple")
        self.unrec_assign_all_btn = QPushButton("הקצה אמן לכולם")
        self.unrec_assign_all_btn.setFixedHeight(28)
        self.unrec_assign_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unrec_assign_all_btn.setProperty("cssClass", "accent")
        urh.addWidget(self.unrec_count_label, 0)
        urh.addWidget(self.unrec_title, 1)
        urh.addWidget(self.unrec_assign_all_btn, 0)
        url.addLayout(urh)

        self.unrec_list = QListWidget()
        self.unrec_list.setObjectName("unrecList")
        self.unrec_list.setMaximumHeight(200)
        url.addWidget(self.unrec_list, 1)

        col.addWidget(self.unrec_panel)

        # initially hide excluded and unrecognized
        self.exc_panel.hide()
        self.unrec_panel.hide()

        return page

    # ─── Connect signals ───
    def _connect_signals(self):
        # sort type
        self.step_sort_type.opts[0].clicked.connect(lambda: self._select_sort_mode("source"))
        self.step_sort_type.opts[1].clicked.connect(lambda: self._select_sort_mode("target"))

        # copy/move
        self.step_copy_move.opts[0].clicked.connect(lambda: self._on_option_changed())
        self.step_copy_move.opts[1].clicked.connect(lambda: self._on_option_changed())

        # artist mode
        for o in self.step_artist_mode.opts:
            o.clicked.connect(lambda: self._on_option_changed())

        # album
        for o in self.step_album.opts:
            o.clicked.connect(lambda: self._on_option_changed())
        self.step_album.opts[2].clicked.connect(lambda: self._animate_albums_folder_row(True))
        self.step_album.opts[0].clicked.connect(lambda: self._animate_albums_folder_row(False))
        self.step_album.opts[1].clicked.connect(lambda: self._animate_albums_folder_row(False))

        # multi
        for o in self.step_multi.opts:
            o.clicked.connect(lambda: self._on_option_changed())

        # file types
        for o in self.step_file_types.opts:
            o.clicked.connect(lambda: self._on_option_changed())

        # subfolders
        for o in self.step_subfolders.opts:
            o.clicked.connect(lambda: self._on_option_changed())

        # target folder
        self.target_browse_btn.clicked.connect(self._choose_target_folder)
        self.target_folder_edit.textChanged.connect(lambda: self._on_option_changed())

        # albums dedicated folder
        self.albums_folder_browse_btn.clicked.connect(self._choose_albums_folder)
        self.albums_folder_edit.textChanged.connect(lambda: self._on_option_changed())

        # navigation
        self.continue_btn.clicked.connect(self._on_continue_clicked)
        self.back_btn.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        # scan / sort
        self.scan_btn.clicked.connect(self._scan_clicked)
        self.sort_btn.clicked.connect(self._sort_clicked)

        # unrecognized assign all
        self.unrec_assign_all_btn.clicked.connect(self._assign_artist_to_all_unrecognized)
    # ─── Selection handlers ───
    def _select_sort_mode(self, mode: str):
        self._sort_mode_selected = mode
        self.step_sort_type.opts[0].setChecked(mode == "source")
        self.step_sort_type.opts[1].setChecked(mode == "target")
        self._animate_target_row(mode == "target")
        self._on_option_changed()

    def _on_option_changed(self):
        self._update_step_completion()
        self._update_summary_text()

    def _animate_target_row(self, show: bool):
        self.target_anim_group.stop()

        if show:
            self.target_row.show()
            self.target_folder_edit.setEnabled(True)
            self.target_browse_btn.setEnabled(True)

            self.target_height_anim.setStartValue(self.target_row.maximumHeight())
            self.target_height_anim.setEndValue(50)
            self.target_fade_anim.setStartValue(self.target_opacity.opacity())
            self.target_fade_anim.setEndValue(1.0)
        else:
            self.target_folder_edit.setEnabled(False)
            self.target_browse_btn.setEnabled(False)

            self.target_height_anim.setStartValue(self.target_row.maximumHeight())
            self.target_height_anim.setEndValue(0)
            self.target_fade_anim.setStartValue(self.target_opacity.opacity())
            self.target_fade_anim.setEndValue(0.0)

        self.target_anim_group.start()

    def _on_target_anim_finished(self):
        if self._sort_mode_selected != "target":
            self.target_row.hide()

    def _animate_albums_folder_row(self, show: bool):
        self.albums_folder_anim_group.stop()

        if show:
            self.albums_folder_row.show()
            self.albums_folder_edit.setEnabled(True)
            self.albums_folder_browse_btn.setEnabled(True)

            self.albums_folder_height_anim.setStartValue(self.albums_folder_row.maximumHeight())
            self.albums_folder_height_anim.setEndValue(50)
            self.albums_folder_fade_anim.setStartValue(self.albums_folder_opacity.opacity())
            self.albums_folder_fade_anim.setEndValue(1.0)
        else:
            self.albums_folder_edit.setEnabled(False)
            self.albums_folder_browse_btn.setEnabled(False)

            self.albums_folder_height_anim.setStartValue(self.albums_folder_row.maximumHeight())
            self.albums_folder_height_anim.setEndValue(0)
            self.albums_folder_fade_anim.setStartValue(self.albums_folder_opacity.opacity())
            self.albums_folder_fade_anim.setEndValue(0.0)

        self.albums_folder_anim_group.start()

    def _on_albums_folder_anim_finished(self):
        if self.step_album.selected_index() != 2:
            self.albums_folder_row.hide()

    def _browse_or_create_folder(self, title: str = "בחר תיקייה") -> str | None:
        """Show a dialog that lets the user browse for an existing folder or create a new one."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dlg.setMinimumWidth(320)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        lbl = QLabel("בחר תיקייה קיימת או צור תיקייה חדשה:")
        lbl.setProperty("cssClass", "labelBold")
        layout.addWidget(lbl)

        btn_existing = QPushButton("עיון — בחר תיקייה קיימת")
        btn_existing.setProperty("cssClass", "primary")
        btn_new = QPushButton("צור תיקייה חדשה")
        btn_new.setProperty("cssClass", "success")
        btn_cancel = QPushButton("ביטול")
        btn_cancel.setProperty("cssClass", "secondary")
        layout.addWidget(btn_existing)
        layout.addWidget(btn_new)
        layout.addWidget(btn_cancel)

        result = [None]

        def browse():
            folder = QFileDialog.getExistingDirectory(dlg, "בחר תיקייה")
            if folder:
                result[0] = folder
            dlg.accept()

        def create_new():
            parent = QFileDialog.getExistingDirectory(dlg, "בחר תיקיית אב לתיקייה החדשה")
            if not parent:
                return

            # דיאלוג מעוצב להזנת שם תיקייה חדשה
            name_dlg = QDialog(dlg)
            name_dlg.setWindowTitle("שם תיקייה חדשה")
            name_dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
            name_dlg.setMinimumWidth(300)
            nd_layout = QVBoxLayout(name_dlg)
            nd_layout.setSpacing(10)
            nd_layout.setContentsMargins(16, 16, 16, 16)

            nd_lbl = QLabel("הזן שם לתיקייה החדשה:")
            nd_lbl.setProperty("cssClass", "labelBold")
            nd_layout.addWidget(nd_lbl)

            nd_edit = HebrewLineEdit()
            nd_edit.setFixedHeight(34)
            nd_layout.addWidget(nd_edit)

            nd_btn_row = QHBoxLayout()
            nd_btn_row.setSpacing(8)
            nd_btn_ok = QPushButton("אישור")
            nd_btn_ok.setProperty("cssClass", "primary")
            nd_btn_cancel = QPushButton("ביטול")
            nd_btn_cancel.setProperty("cssClass", "secondary")
            nd_btn_ok.clicked.connect(name_dlg.accept)
            nd_btn_cancel.clicked.connect(name_dlg.reject)
            nd_btn_row.addStretch()
            nd_btn_row.addWidget(nd_btn_cancel)
            nd_btn_row.addWidget(nd_btn_ok)
            nd_layout.addLayout(nd_btn_row)

            nd_edit.returnPressed.connect(name_dlg.accept)

            if name_dlg.exec() != QDialog.DialogCode.Accepted:
                return
            name = nd_edit.text().strip()
            if not name:
                return

            new_folder = os.path.join(parent, name)
            try:
                os.makedirs(new_folder, exist_ok=True)
                result[0] = new_folder
            except Exception as e:
                QMessageBox.warning(dlg, "שגיאה", f"לא ניתן ליצור תיקייה: {e}")
                return
            dlg.accept()

        btn_existing.clicked.connect(browse)
        btn_new.clicked.connect(create_new)
        btn_cancel.clicked.connect(dlg.reject)
        dlg.exec()
        return result[0]

    def _choose_target_folder(self):
        folder = self._browse_or_create_folder("בחר תיקיית יעד")
        if folder:
            self.target_folder_edit.setText(folder)

    def _choose_albums_folder(self):
        folder = self._browse_or_create_folder("בחר תיקיית אלבומים ייעודית")
        if folder:
            self.albums_folder_edit.setText(folder)

    # ─── Step completion + summary ───
    def _update_step_completion(self):
        sort_done = self._sort_mode_selected in {"source", "target"}
        self.step_sort_type.set_completed(sort_done)

        target_done = False
        if self._sort_mode_selected == "target":
            t = self.target_folder_edit.text().strip()
            target_done = bool(t) and os.path.isdir(t)
        self.target_indicator.set_checked_animated(target_done if self._sort_mode_selected == "target" else False)

        self.step_copy_move.set_completed(self.step_copy_move.has_selection())
        self.step_artist_mode.set_completed(self.step_artist_mode.has_selection())
        self.step_album.set_completed(self.step_album.has_selection())
        self.step_multi.set_completed(self.step_multi.has_selection())
        self.step_file_types.set_completed(self.step_file_types.has_selection())
        self.step_subfolders.set_completed(self.step_subfolders.has_selection())

        # albums dedicated folder indicator
        albums_folder_done = False
        if self.step_album.selected_index() == 2:
            af = self.albums_folder_edit.text().strip()
            albums_folder_done = bool(af) and os.path.isdir(af)
        self.albums_folder_indicator.set_checked_animated(albums_folder_done if self.step_album.selected_index() == 2 else False)

    def _update_summary_text(self):
        parts = []

        si = self.step_sort_type.selected_index()
        if si == 0: parts.append("מיון בתיקיית מקור")
        elif si == 1: parts.append("מיון לתיקיית יעד")

        si = self.step_copy_move.selected_index()
        if si == 0: parts.append("העתקה")
        elif si == 1: parts.append("העברה")

        si = self.step_artist_mode.selected_index()
        if si == 0: parts.append("רשימת אמנים")
        elif si == 1: parts.append("תיקיות קיימות")
        elif si == 2: parts.append("Metadata")

        si = self.step_album.selected_index()
        if si == 0: parts.append("אלבומים בתיקיית האמן")
        elif si == 1: parts.append("אלבומים ללא טיפול")
        elif si == 2: parts.append("אלבומים בתיקייה ייעודית")

        si = self.step_multi.selected_index()
        if si == 0: parts.append("לכל האמנים")
        elif si == 1: parts.append("לאמן הראשון")
        elif si == 2: parts.append("שאל בכל פעם")

        si = self.step_file_types.selected_index()
        if si == 0: parts.append("רק שירים")
        elif si == 1: parts.append("שירים + וידאו")

        si = self.step_subfolders.selected_index()
        if si == 0: parts.append("כולל תתי תיקיות")
        elif si == 1: parts.append("רק תיקיית מקור")

        if self._sort_mode_selected == "target":
            t = self.target_folder_edit.text().strip()
            if t:
                parts.append("יעד תקין ✓" if os.path.isdir(t) else "יעד לא תקין ✗")

        if self.step_album.selected_index() == 2:
            af = self.albums_folder_edit.text().strip()
            if af:
                parts.append("תיקיית אלבומים תקינה ✓" if os.path.isdir(af) else "תיקיית אלבומים לא תקינה ✗")

        self.summary_label.setText(" · ".join(parts) if parts else "בחר את כל ההגדרות כדי להמשיך")

    # ─── Continue to scan ───
    def _on_continue_clicked(self):
        if not self._validate_before_scan():
            return
        self.stack.setCurrentIndex(1)
        self._scan_clicked()

    # ─── Helpers ───
    def _get_source_folder(self) -> str:
        main_window = self.window()
        return getattr(getattr(main_window, "folder_selector", None), "current_folder", "") or ""

    def _collect_options(self) -> dict:
        return {
            "sort_in_source": self.step_sort_type.selected_index() == 0,
            "sort_to_target": self.step_sort_type.selected_index() == 1,
            "target_folder": self.target_folder_edit.text().strip(),
            "copy_mode": self.step_copy_move.selected_index() == 0,
            "move_mode": self.step_copy_move.selected_index() == 1,
            "use_artist_list": self.step_artist_mode.selected_index() == 0,
            "only_existing_artist_folders": self.step_artist_mode.selected_index() == 1,
            "use_metadata": self.step_artist_mode.selected_index() == 2,
            "album_into_artist": self.step_album.selected_index() == 0,
            "album_regular": self.step_album.selected_index() == 1,
            "album_dedicated_folder": self.step_album.selected_index() == 2,
            "albums_folder": self.albums_folder_edit.text().strip(),
            "multi_to_all": self.step_multi.selected_index() == 0,
            "multi_first_only": self.step_multi.selected_index() == 1,
            "multi_ask_each_time": self.step_multi.selected_index() == 2,
            "file_types_audio_only": self.step_file_types.selected_index() == 0,
            "file_types_audio_video": self.step_file_types.selected_index() == 1,
            "include_subfolders": self.step_subfolders.selected_index() == 0,
            "source_folder_only": self.step_subfolders.selected_index() == 1,
        }

    def _validate_before_scan(self) -> bool:
        if self._sort_mode_selected not in {"source", "target"}:
            self._show_warning("בחר קודם סוג מיון.")
            return False

        source_folder = self._get_source_folder().strip()
        if not source_folder or not os.path.isdir(source_folder):
            self._show_warning("בחר קודם תיקיית מקור חוקית בחלק העליון של החלון.")
            return False

        if not self.step_copy_move.has_selection():
            self._show_warning("בחר האם לבצע העתקה או העברה.")
            return False

        if not self.step_artist_mode.has_selection():
            self._show_warning("בחר אופן זיהוי אמנים.")
            return False

        if not self.step_album.has_selection():
            self._show_warning("בחר מה לעשות עם אלבומים.")
            return False

        if not self.step_multi.has_selection():
            self._show_warning("בחר מה לעשות עם שירים בעלי כמה אמנים.")
            return False

        if not self.step_file_types.has_selection():
            self._show_warning("בחר אילו סוגי קבצים לסרוק.")
            return False

        if not self.step_subfolders.has_selection():
            self._show_warning("בחר האם לכלול תתי תיקיות.")
            return False

        if self._sort_mode_selected == "target":
            target = self.target_folder_edit.text().strip()
            if not target:
                self._show_warning("בחר תיקיית יעד.")
                return False
            if not os.path.isdir(target):
                self._show_warning("תיקיית היעד אינה חוקית.")
                return False

        if self.step_album.selected_index() == 2:
            af = self.albums_folder_edit.text().strip()
            if not af:
                self._show_warning("בחר תיקיית אלבומים ייעודית.")
                return False
            if not os.path.isdir(af):
                self._show_warning("תיקיית האלבומים הייעודית אינה חוקית.")
                return False

        return True

    # ─── Scan logic ───
    def _scan_music_files(
        self,
        folder: str,
        extensions: set[str] | None = None,
        include_subfolders: bool = True,
    ) -> list[str]:
        if extensions is None:
            extensions = self.SUPPORTED_EXTENSIONS
        files: list[str] = []
        root = Path(folder)
        paths = root.rglob("*") if include_subfolders else root.iterdir()
        for path in paths:
            if path.is_file() and path.suffix.lower() in extensions:
                files.append(str(path))
        return sorted(files)

    def _extract_artists_from_filename(self, filepath: str) -> list[str]:
        filename = os.path.splitext(os.path.basename(filepath))[0]
        normalized_filename = filename.casefold()
        # Also create a version with _, -, – replaced by space for broader matching
        normalized_spaces = re.sub(r"[_\-–]", " ", filename).casefold()
        matched_artists: list[str] = []

        artists_set = getattr(self.artists_tab, "_artists_set", set())
        aliases_map = getattr(self.artists_tab, "_aliases_map", {})

        for artist in sorted(artists_set, key=len, reverse=True):
            artist_cf = artist.casefold()
            if artist not in matched_artists and (artist_cf in normalized_filename or artist_cf in normalized_spaces):
                matched_artists.append(artist)

        for owner, aliases in aliases_map.items():
            for alias in aliases:
                alias_cf = alias.casefold()
                if owner not in matched_artists and (alias_cf in normalized_filename or alias_cf in normalized_spaces):
                    matched_artists.append(owner)

        return matched_artists

    def _extract_artists_from_metadata(self, filepath: str) -> list[str]:
        try:
            import mutagen
            audio = mutagen.File(filepath, easy=True)
            if audio is None:
                return []
            artists: list[str] = []
            for tag in ("artist", "albumartist", "performer"):
                values = audio.get(tag, [])
                for value in values:
                    for part in value.replace("/", ";").replace(",", ";").split(";"):
                        name = part.strip()
                        if name and name not in artists:
                            artists.append(name)
            return artists
        except Exception:
            return []

    def _existing_artist_folders(self, folder: str) -> set[str]:
        existing: set[str] = set()
        root = Path(folder)
        if not root.exists() or not root.is_dir():
            return existing
        for child in root.iterdir():
            if child.is_dir():
                existing.add(child.name.strip())
        return existing

    def _animate_results_refresh(self):
        self.results_fade_anim = QPropertyAnimation(self.results_opacity, b"opacity", self)
        self.results_fade_anim.setDuration(200)
        self.results_fade_anim.setStartValue(0.0)
        self.results_fade_anim.setEndValue(1.0)
        self.results_fade_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.results_fade_anim.start()

    def _update_results_empty_state(self):
        has_items = self.scanned_artists_list.count() > 0
        self.empty_results_label.setVisible(not has_items)

    def _set_scan_status(self, text: str):
        self.status_label.setText(f"📊  {text}")

    def _scan_clicked(self):
        if not self._validate_before_scan():
            return

        source_folder = self._get_source_folder().strip()
        options = self._collect_options()

        # Determine extension set based on file-type selection
        if options["file_types_audio_video"]:
            extensions = self.AUDIO_EXTENSIONS | self.VIDEO_EXTENSIONS
        else:
            extensions = self.AUDIO_EXTENSIONS

        include_subfolders = options["include_subfolders"]

        files = self._scan_music_files(source_folder, extensions, include_subfolders)

        if not files:
            self._scan_results.clear()
            self._excluded_artists.clear()
            self._refresh_scan_results_ui()
            self._set_scan_status("לא נמצאו קבצי מוזיקה בתיקיית המקור.")
            self.empty_results_label.setText("לא נמצאו קבצי מוזיקה לסריקה")
            self._update_results_empty_state()
            self._show_info("סריקה", "לא נמצאו קבצי מוזיקה בתיקייה.")
            return

        total = len(files)

        # Progress dialog for the artist-identification phase
        progress = QProgressDialog("סורק קבצים...", "ביטול", 0, total, self)
        progress.setWindowTitle("סריקה")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(500)
        progress.setValue(0)

        artist_to_songs: dict[str, list[str]] = {}

        if options["use_artist_list"]:
            valid_artists = getattr(self.artists_tab, "_artists_set", set())
            aliases_map = getattr(self.artists_tab, "_aliases_map", {})
            valid_lower = {a.casefold(): a for a in valid_artists}
            alias_lower = {
                alias.casefold(): owner
                for owner, aliases in aliases_map.items()
                for alias in aliases
            }

        for i, filepath in enumerate(files):
            if progress.wasCanceled():
                progress.close()
                self._set_scan_status("הסריקה בוטלה.")
                return

            if i % 50 == 0:
                progress.setValue(i)
                QApplication.processEvents()

            matched_artists: list[str] = []

            if options["use_metadata"]:
                matched_artists = self._extract_artists_from_metadata(filepath)
            elif options["use_artist_list"]:
                for artist in self._extract_artists_from_filename(filepath):
                    if artist in valid_artists and artist not in matched_artists:
                        matched_artists.append(artist)
                for meta_artist in self._extract_artists_from_metadata(filepath):
                    meta_lower = meta_artist.casefold()
                    if meta_lower in valid_lower:
                        artist = valid_lower[meta_lower]
                        if artist not in matched_artists:
                            matched_artists.append(artist)
                    elif meta_lower in alias_lower:
                        owner = alias_lower[meta_lower]
                        if owner not in matched_artists:
                            matched_artists.append(owner)
            else:
                existing_folders = self._existing_artist_folders(source_folder)
                for artist in self._extract_artists_from_filename(filepath):
                    if artist in existing_folders and artist not in matched_artists:
                        matched_artists.append(artist)

            for artist in matched_artists:
                if artist not in artist_to_songs:
                    artist_to_songs[artist] = []
                if filepath not in artist_to_songs[artist]:
                    artist_to_songs[artist].append(filepath)

        progress.setValue(total)
        progress.close()

        # Collect unrecognized files (those not matched to any artist)
        matched_files: set[str] = set()
        for songs in artist_to_songs.values():
            matched_files.update(songs)
        self._unrecognized_files = [fp for fp in files if fp not in matched_files]

        self._scan_results = dict(sorted(artist_to_songs.items()))
        self._excluded_artists.clear()
        self._refresh_scan_results_ui()

        total_artists = len(self._scan_results)
        total_songs = sum(len(songs) for songs in self._scan_results.values())

        # build status with options summary
        opt_parts = []
        si = self.step_sort_type.selected_index()
        opt_parts.append("בתיקיית מקור" if si == 0 else "לתיקיית יעד")
        si = self.step_copy_move.selected_index()
        opt_parts.append("העתקה" if si == 0 else "העברה")
        si = self.step_artist_mode.selected_index()
        opt_parts.append(["רשימת אמנים", "תיקיות קיימות", "Metadata"][si] if si >= 0 else "")
        opts_str = " · ".join(p for p in opt_parts if p)

        if total_artists > 0:
            status_parts = [
                f"נסרקו {len(files)} קבצים",
                f"זוהו {total_artists} אמנים",
                f"{total_songs} שירים למיון",
                opts_str,
            ]
            if self._unrecognized_files:
                status_parts.append(f"{len(self._unrecognized_files)} שירים לא מזוהים")
            self._set_scan_status("  ·  ".join(p for p in status_parts if p))
        else:
            self._set_scan_status(
                f"נסרקו {len(files)} קבצים, אך לא זוהו אמנים תואמים לפי ההגדרות שנבחרו."
            )
            self.empty_results_label.setText("לא זוהו אמנים תואמים לפי ההגדרות שנבחרו")

        self._update_results_empty_state()
        self._animate_results_refresh()

    def _refresh_scan_results_ui(self):
        self.scanned_artists_list.clear()

        for artist_name, songs in sorted(self._scan_results.items()):
            row_widget = ScannedArtistRow(artist_name, songs, is_excluded=False)
            row_widget.removeRequested.connect(self._exclude_artist)

            item = QListWidgetItem()
            row_widget.adjustSize()
            item.setSizeHint(QSize(0, row_widget.sizeHint().height() + 6))
            self.scanned_artists_list.addItem(item)
            self.scanned_artists_list.setItemWidget(item, row_widget)

        self.result_count_label.setText(f"{len(self._scan_results)} אמנים")

        self.excluded_artists_list.clear()

        for artist_name, songs in sorted(self._excluded_artists.items()):
            row_widget = ScannedArtistRow(artist_name, songs, is_excluded=True)
            row_widget.restoreRequested.connect(self._restore_artist)

            item = QListWidgetItem()
            row_widget.adjustSize()
            item.setSizeHint(QSize(0, row_widget.sizeHint().height() + 4))
            self.excluded_artists_list.addItem(item)
            self.excluded_artists_list.setItemWidget(item, row_widget)

        self.excluded_count_label.setText(f"{len(self._excluded_artists)} אמנים")

        has_excluded = len(self._excluded_artists) > 0
        self.exc_panel.setVisible(has_excluded)

        # Unrecognized files panel
        self.unrec_list.clear()
        for filepath in self._unrecognized_files:
            row_widget = UnrecognizedFileRow(filepath)
            row_widget.assignRequested.connect(self._assign_artist_to_file)
            item = QListWidgetItem()
            row_widget.adjustSize()
            item.setSizeHint(QSize(0, row_widget.sizeHint().height() + 4))
            self.unrec_list.addItem(item)
            self.unrec_list.setItemWidget(item, row_widget)
        self.unrec_count_label.setText(f"{len(self._unrecognized_files)} שירים")
        self.unrec_panel.setVisible(len(self._unrecognized_files) > 0)

        self._update_results_empty_state()

    def _exclude_artist(self, artist_name: str):
        if artist_name not in self._scan_results:
            return
        songs = self._scan_results.pop(artist_name)
        self._excluded_artists[artist_name] = songs
        self._refresh_scan_results_ui()

        total_songs = sum(len(s) for s in self._scan_results.values())
        self._set_scan_status(
            f"{len(self._scan_results)} אמנים למיון ({total_songs} שירים) · "
            f"{len(self._excluded_artists)} אמנים הוחרגו"
        )

    def _restore_artist(self, artist_name: str):
        if artist_name not in self._excluded_artists:
            return
        songs = self._excluded_artists.pop(artist_name)
        self._scan_results[artist_name] = songs
        self._refresh_scan_results_ui()

        total_songs = sum(len(s) for s in self._scan_results.values())
        self._set_scan_status(
            f"{len(self._scan_results)} אמנים למיון ({total_songs} שירים) · "
            f"{len(self._excluded_artists)} אמנים הוחרגו"
        )

    def _assign_artist_to_file(self, filepath: str) -> bool:
        """Show dialog to assign an artist to an unrecognized file. Returns True if assigned."""
        existing_artists = sorted(getattr(self.artists_tab, "_artists_set", set()))
        dlg = AssignArtistDialog(os.path.basename(filepath), existing_artists, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False

        artist_name = dlg.get_artist_name()
        if not artist_name:
            return False

        # Add artist to list if new
        if self.artists_tab is not None and hasattr(self.artists_tab, "_sanitize_artist_name"):
            sanitized = self.artists_tab._sanitize_artist_name(artist_name)
            if sanitized:
                artist_name = sanitized
                if sanitized not in getattr(self.artists_tab, "_artists_set", set()):
                    self.artists_tab._add_artist_to_list(sanitized, persist=True)
            else:
                self._show_warning(f'שם האמן "{artist_name}" אינו תקין.')
                return False

        # Add file to scan_results for this artist
        if artist_name not in self._scan_results:
            self._scan_results[artist_name] = []
        if filepath not in self._scan_results[artist_name]:
            self._scan_results[artist_name].append(filepath)

        # Remove from unrecognized list
        if filepath in self._unrecognized_files:
            self._unrecognized_files.remove(filepath)

        self._refresh_scan_results_ui()
        return True

    def _assign_artist_to_all_unrecognized(self):
        """Assign artists to all unrecognized files one by one."""
        if not self._unrecognized_files:
            return
        for filepath in list(self._unrecognized_files):
            self._assign_artist_to_file(filepath)

        # ═══════════════════════════════════════════════
    #  Sorting execution
    # ═══════════════════════════════════════════════

    def _sort_clicked(self):
        """הפעלת המיון בפועל על בסיס תוצאות הסריקה."""
        if not self._scan_results:
            self._show_warning("אין תוצאות סריקה. בצע סריקה קודם.")
            return

        options = self._collect_options()
        source_folder = self._get_source_folder().strip()

        if not source_folder or not os.path.isdir(source_folder):
            self._show_warning("תיקיית המקור אינה חוקית.")
            return

        # קביעת תיקיית היעד
        if options["sort_to_target"]:
            target_folder = options["target_folder"]
            if not target_folder or not os.path.isdir(target_folder):
                self._show_warning("תיקיית היעד אינה חוקית.")
                return
        else:
            target_folder = source_folder

        copy_mode = options["copy_mode"]
        album_into_artist = options["album_into_artist"]
        album_dedicated_folder = options["album_dedicated_folder"]
        albums_folder = options.get("albums_folder", "")
        multi_ask_each_time = options["multi_ask_each_time"]
        multi_first_only = options["multi_first_only"]

        # --- בניית מפה הפוכה: קובץ → רשימת אמנים ---
        file_to_artists: dict[str, list[str]] = {}
        for artist_name, songs in self._scan_results.items():
            for filepath in songs:
                if filepath not in file_to_artists:
                    file_to_artists[filepath] = []
                if artist_name not in file_to_artists[filepath]:
                    file_to_artists[filepath].append(artist_name)

        # --- קביעת אמנים לכל קובץ לפי הגדרת ריבוי אמנים ---
        if multi_ask_each_time:
            file_chosen_artists: dict[str, list[str]] = {}
            for filepath, artists in file_to_artists.items():
                if len(artists) > 1:
                    dlg = MultiArtistChooserDialog(
                        os.path.basename(filepath), artists, self
                    )
                    if dlg.exec() == QDialog.DialogCode.Accepted:
                        chosen = dlg.selected_artists()
                        file_chosen_artists[filepath] = chosen if chosen else []
                    else:
                        file_chosen_artists[filepath] = []  # דלג על קובץ זה
                else:
                    file_chosen_artists[filepath] = artists
        elif multi_first_only:
            file_chosen_artists = {
                fp: ([artists[0]] if artists else [])
                for fp, artists in file_to_artists.items()
            }
        else:  # multi_to_all (ברירת מחדל)
            file_chosen_artists = dict(file_to_artists)

        # --- טיפול באלבומים ללא אמן משותף (אפשרות 1) ---
        album_single_folder_override: dict[str, str] = {}   # filepath → override folder
        album_skip_files: set[str] = set()                  # filepaths to skip entirely
        asked_album_names: set[str] = set()                 # שמות אלבומים שנשאל עליהם המשתמש

        use_album_logic = album_into_artist or album_dedicated_folder
        if use_album_logic:
            # Build album → list of files
            album_to_files: dict[str, list[str]] = {}
            for filepath, chosen_artists in file_chosen_artists.items():
                if not chosen_artists:
                    continue
                album_name = self._detect_album_name(filepath)
                if not album_name:
                    continue
                if album_name not in album_to_files:
                    album_to_files[album_name] = []
                album_to_files[album_name].append(filepath)

            # For each album with ≥2 files, check if they share a common artist
            for album_name, album_files in album_to_files.items():
                if len(album_files) < 2:
                    continue
                file_artist_sets = [set(file_chosen_artists.get(fp, [])) for fp in album_files]
                common_artists = file_artist_sets[0].copy()
                for artist_set in file_artist_sets[1:]:
                    common_artists &= artist_set

                if not common_artists:
                    # No common artist — ask the user
                    asked_album_names.add(album_name)
                    dlg = AlbumNoCommonArtistDialog(album_name, album_files, self)
                    dlg.exec()
                    choice, folder_path = dlg.get_choice()
                    if choice == "single_folder" and folder_path:
                        # שדרוג 4: יצירת תיקיית משנה עם שם האלבום בתוך התיקייה שנבחרה
                        # album_name כבר עבר ניקוי תווים אסורים דרך _detect_album_name → _sanitize_folder_name
                        album_dest = os.path.join(folder_path, album_name)
                        for fp in album_files:
                            album_single_folder_override[fp] = album_dest
                    elif choice == "skip":
                        album_skip_files.update(album_files)
                    # "sort_artists" → no change, normal sort

        # --- Pre-scan לאלבומים: ספירת שירים לכל (אמן, אלבום) ---
        album_song_counts: dict[tuple[str, str], int] = {}
        if use_album_logic:
            for filepath, chosen_artists in file_chosen_artists.items():
                if not chosen_artists or filepath in album_skip_files:
                    continue
                album_name = self._detect_album_name(filepath)
                if album_name:
                    for artist in chosen_artists:
                        key = (artist, album_name)
                        album_song_counts[key] = album_song_counts.get(key, 0) + 1

        # --- חלון התקדמות ---
        total_files = len(file_chosen_artists)
        progress = QProgressDialog("ממיין שירים...", "ביטול", 0, total_files, self)
        progress.setWindowTitle("מיון")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        sorted_count = 0
        skipped_count = 0
        error_count = 0
        errors: list[str] = []
        cancelled = False

        # Begin undo batch
        action_desc = "העתקת" if copy_mode else "העברת"
        if self._undo_manager:
            self._undo_manager.begin_batch(f"מיון שירים — {action_desc} {total_files} קבצים")
        _created_dirs: set[str] = set()

        for proc_idx, (filepath, chosen_artists) in enumerate(file_chosen_artists.items()):
            if progress.wasCanceled():
                cancelled = True
                break

            progress.setValue(proc_idx)
            QApplication.processEvents()

            if not chosen_artists:
                skipped_count += 1
                continue

            if filepath in album_skip_files:
                skipped_count += 1
                continue

            if not os.path.isfile(filepath):
                skipped_count += 1
                continue

            filename = os.path.basename(filepath)
            # cache album detection for this file
            album_name = self._detect_album_name(filepath) if use_album_logic else None

            current_source = filepath  # tracks the file's actual location; updated after the first move (multi-artist move mode)

            try:
                for i, artist_name in enumerate(chosen_artists):
                    artist_folder = os.path.join(target_folder, artist_name)

                    # --- override: single folder for this album ---
                    if filepath in album_single_folder_override:
                        dest_folder = album_single_folder_override[filepath]
                    # --- dedicated albums folder ---
                    elif album_dedicated_folder and album_name and albums_folder:
                        key = (artist_name, album_name)
                        if album_song_counts.get(key, 0) >= 3:
                            dest_folder = os.path.join(albums_folder, artist_name, album_name)
                        else:
                            dest_folder = artist_folder
                    # --- album into artist ---
                    elif album_into_artist and album_name:
                        dest_folder = artist_folder
                        key = (artist_name, album_name)
                        if album_song_counts.get(key, 0) >= 3:
                            dest_folder = os.path.join(artist_folder, album_name)
                    else:
                        dest_folder = artist_folder

                    if not os.path.isdir(dest_folder):
                        os.makedirs(dest_folder, exist_ok=True)
                        if self._undo_manager and dest_folder not in _created_dirs:
                            self._undo_manager.record_mkdir(dest_folder)
                            _created_dirs.add(dest_folder)
                    dest_path = self._get_unique_dest_path(
                        os.path.join(dest_folder, filename)
                    )

                    if copy_mode:
                        shutil.copy2(filepath, dest_path)
                        if self._undo_manager:
                            self._undo_manager.record_copy(filepath, dest_path)
                    else:
                        if i == 0:
                            shutil.move(current_source, dest_path)
                            if self._undo_manager:
                                self._undo_manager.record_move(current_source, dest_path)
                            current_source = dest_path  # עדכון מיקום הקובץ
                        else:
                            # לאחר ההעברה הראשונה — העתקה מהמיקום החדש
                            shutil.copy2(current_source, dest_path)
                            if self._undo_manager:
                                self._undo_manager.record_copy(current_source, dest_path)

                sorted_count += 1

            except Exception as e:
                error_count += 1
                errors.append(f"{filename}: {e}")

        progress.setValue(total_files)
        progress.close()

        # End undo batch
        if self._undo_manager:
            self._undo_manager.end_batch()

        # --- שדרוג 3: הסרת שירים לא מזוהים ששייכים לאלבומים שנשאל עליהם המשתמש ---
        if use_album_logic and asked_album_names and self._unrecognized_files:
            still_unrecognized = []
            for fp in self._unrecognized_files:
                album = self._detect_album_name(fp)
                if album and album in asked_album_names:
                    pass  # השיר שייך לאלבום שטופל — לא להציגו שוב כלא מזוהה
                else:
                    still_unrecognized.append(fp)
            if len(still_unrecognized) != len(self._unrecognized_files):
                self._unrecognized_files = still_unrecognized
                self._refresh_scan_results_ui()

        # --- סיכום ---
        action_word = "הועתקו" if copy_mode else "הועברו"
        summary_parts = [f"{action_word} {sorted_count} שירים בהצלחה"]

        if cancelled:
            summary_parts.insert(0, "המיון בוטל —")

        if skipped_count > 0:
            summary_parts.append(f"{skipped_count} קבצים דולגו (לא נמצאו)")

        if error_count > 0:
            summary_parts.append(f"{error_count} שגיאות")

        summary = " · ".join(summary_parts)
        self._set_scan_status(summary)

        if errors:
            error_details = "\n".join(errors[:20])
            if len(errors) > 20:
                error_details += f"\n... ועוד {len(errors) - 20} שגיאות"
            self._show_info(
                "המיון הסתיים עם שגיאות",
                f"{summary}<br><br><small>{error_details}</small>",
            )
        else:
            self._show_info("המיון הושלם", summary)

    def _detect_album_name(self, filepath: str) -> str | None:
        """ניסיון לזהות שם אלבום מ-metadata של הקובץ."""
        try:
            import mutagen
            audio = mutagen.File(filepath, easy=True)
            if audio is None:
                return None

            album_values = audio.get("album", [])
            if album_values:
                album_name = album_values[0].strip()
                if album_name:
                    # ניקוי תווים לא חוקיים לשמות תיקיות
                    return self._sanitize_folder_name(album_name)
            return None
        except Exception:
            return None

    def _sanitize_folder_name(self, name: str) -> str:
        """ניקוי שם לשימוש כתיקייה — הסרת תווים אסורים."""
        forbidden = '<>:"/\\|?*'
        cleaned = "".join(ch if ch not in forbidden else "_" for ch in name)
        cleaned = cleaned.strip(". ")
        return cleaned if cleaned else None

    def _get_unique_dest_path(self, dest_path: str) -> str:
        """אם הקובץ כבר קיים ביעד, הוסף מספר לשם."""
        if not os.path.exists(dest_path):
            return dest_path

        base, ext = os.path.splitext(dest_path)
        counter = 1
        while True:
            new_path = f"{base} ({counter}){ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1
            if counter > 9999:
                return dest_path  # fallback
