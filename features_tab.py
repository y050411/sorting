import os
import re
import shutil
import hashlib
import math
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QMessageBox, QRadioButton, QButtonGroup,
    QFrame, QInputDialog, QDialog, QTextEdit, QDialogButtonBox, QScrollArea,
    QProgressDialog, QFileDialog, QComboBox, QSpinBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

try:
    from pydub import AudioSegment
    from pydub.silence import detect_leading_silence
except Exception:
    AudioSegment = None
    detect_leading_silence = None

from shared import HebrewLineEdit

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg",
    ".opus", ".wav", ".aiff", ".aif",
}

# Pre-compiled regexes for stem edge-cleaning (option 5).
# Allowed edge characters: Hebrew letters (U+05D0–U+05EA),
# Hebrew apostrophe ׳ (U+05F3), Hebrew double-apostrophe ״ (U+05F4),
# Latin letters A-Za-z, straight single/double quote.
_RE_DOUBLE_SPACE = re.compile(r" {2,}")
_RE_TRIM_START   = re.compile("^[^\u05D0-\u05EA\u05F3\u05F4A-Za-z'\"]+")
_RE_TRIM_END     = re.compile("[^\u05D0-\u05EA\u05F3\u05F4A-Za-z'\"]+$")
_RE_LEADING_NUMBER = re.compile(r"^(\d+)")

# Word-boundary lookarounds compatible with Hebrew and Latin scripts.
# These ensure a match is not part of a longer word in either script.
_WB_BEFORE = r"(?<![א-תA-Za-z\d])"
_WB_AFTER  = r"(?![א-תA-Za-z\d])"

# Maximum number of items shown in a truncated message box list
# (prevents the dialog from becoming too tall to be usable).
_MAX_MSG_ITEMS = 20
_HASH_CHUNK_SIZE = 1024 * 1024
_ALBUM_ART_SIZE = 130
_PROGRESS_EVENTS_STEP = 25
_SILENCE_DBFS_FOR_SILENT = -50
_SILENCE_DBFS_OFFSET = 16
_SILENCE_CHUNK_MS = 10
_AUDIO_SIGNATURE_SAMPLE_RATIO = 0.2

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

_BTN_PRIMARY = """
QPushButton {
    background: #4682b4; color: #fff; border-radius: 8px;
    padding: 9px 36px; font-size: 16px; font-weight: 700;
}
QPushButton:hover    { background: #1e4972; }
QPushButton:disabled { background: #b0c4d8; }
"""

_INPUT_STYLE = (
    "font-size: 14px; padding: 5px 8px; border-radius: 6px;"
    " background: #fff; border: 1px solid #ccc;"
)

_CB_STYLE  = "font-size: 15px; color: #1c355e;"
_RB_STYLE  = "font-size: 13px; color: #333;"
_LBL_SMALL = "font-size: 13px; color: #444;"


# ---------------------------------------------------------------------------
# FeaturesTab
# ---------------------------------------------------------------------------

class FeaturesTab(QWidget):
    def __init__(self, artists_tab, parent: QWidget | None = None):
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self._artists_tab = artists_tab
        self._metadata_cache: dict[Path, list[str]] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # ── Page title ────────────────────────────────────────────────────
        title = QLabel("תיקון שמות")
        title.setStyleSheet(
            "font-size: 24px; font-weight: 900; color: #1c355e;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(title)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)

        # ── Card ─────────────────────────────────────────────────────────
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: #f0f5fb;
                border: 1.5px solid #c3d5ee;
                border-radius: 12px;
            }
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 18, 20, 18)
        cl.setSpacing(10)

        ops_label = QLabel("בחר פעולות לביצוע:")
        ops_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #2c4a6e;"
            " border: none;"
        )
        cl.addWidget(ops_label)

        # ── Checkbox 1 ────────────────────────────────────────────────────
        self._cb1 = QCheckBox("הסרת שם האמן משמות הקבצים")
        self._cb1.setStyleSheet(_CB_STYLE)
        cl.addWidget(self._cb1)

        # ── Checkbox 2 + sub-options ──────────────────────────────────────
        self._cb2 = QCheckBox("הוספת שם אמן לשמות קבצים")
        self._cb2.setStyleSheet(_CB_STYLE)
        cl.addWidget(self._cb2)

        self._opt2 = QWidget()
        self._opt2.setStyleSheet("QWidget { background: transparent; border: none; }")
        o2 = QVBoxLayout(self._opt2)
        o2.setContentsMargins(26, 2, 4, 2)
        o2.setSpacing(5)

        row2a = QHBoxLayout()
        row2a.setSpacing(14)
        self._add_pos_grp = QButtonGroup(self)
        self._add_start_rb = QRadioButton("בתחילת שם הקובץ")
        self._add_end_rb   = QRadioButton("בסוף שם הקובץ")
        self._add_start_rb.setChecked(True)
        for rb in (self._add_start_rb, self._add_end_rb):
            rb.setStyleSheet(_RB_STYLE)
            self._add_pos_grp.addButton(rb)
            row2a.addWidget(rb)
        row2a.addStretch()
        o2.addLayout(row2a)

        row2b = QHBoxLayout()
        row2b.setSpacing(8)
        sep_lbl = QLabel("מפריד:")
        sep_lbl.setStyleSheet(_LBL_SMALL)
        self._add_sep = HebrewLineEdit()
        self._add_sep.setText(" - ")
        self._add_sep.setMaximumWidth(90)
        self._add_sep.setStyleSheet(_INPUT_STYLE)
        row2b.addWidget(sep_lbl)
        row2b.addWidget(self._add_sep)
        row2b.addStretch()
        o2.addLayout(row2b)

        self._opt2.setVisible(False)
        cl.addWidget(self._opt2)
        self._cb2.toggled.connect(self._opt2.setVisible)

        # ── Checkbox 3 + sub-options ──────────────────────────────────────
        self._cb3 = QCheckBox("מחיקת תווים משמות קבצים")
        self._cb3.setStyleSheet(_CB_STYLE)
        cl.addWidget(self._cb3)

        self._opt3 = QWidget()
        self._opt3.setStyleSheet("QWidget { background: transparent; border: none; }")
        o3 = QHBoxLayout(self._opt3)
        o3.setContentsMargins(26, 2, 4, 2)
        o3.setSpacing(8)
        lbl3 = QLabel("תווים למחיקה:")
        lbl3.setStyleSheet(_LBL_SMALL)
        self._del_chars = HebrewLineEdit()
        self._del_chars.setPlaceholderText("למשל: _#!")
        self._del_chars.setMaximumWidth(220)
        self._del_chars.setStyleSheet(_INPUT_STYLE)
        o3.addWidget(lbl3)
        o3.addWidget(self._del_chars)
        o3.addStretch()

        self._opt3.setVisible(False)
        cl.addWidget(self._opt3)
        self._cb3.toggled.connect(self._opt3.setVisible)

        # ── Checkbox 4 + sub-options ──────────────────────────────────────
        self._cb4 = QCheckBox("מחיקת מילים משמות קבצים")
        self._cb4.setStyleSheet(_CB_STYLE)
        cl.addWidget(self._cb4)

        self._opt4 = QWidget()
        self._opt4.setStyleSheet("QWidget { background: transparent; border: none; }")
        o4 = QHBoxLayout(self._opt4)
        o4.setContentsMargins(26, 2, 4, 2)
        o4.setSpacing(8)
        lbl4 = QLabel("מילה / ביטוי למחיקה:")
        lbl4.setStyleSheet(_LBL_SMALL)
        self._del_word = HebrewLineEdit()
        self._del_word.setPlaceholderText("למשל: remix")
        self._del_word.setMaximumWidth(280)
        self._del_word.setStyleSheet(_INPUT_STYLE)
        o4.addWidget(lbl4)
        o4.addWidget(self._del_word)
        o4.addStretch()

        self._opt4.setVisible(False)
        cl.addWidget(self._opt4)
        self._cb4.toggled.connect(self._opt4.setVisible)

        # ── Checkboxes 5 & 6 ─────────────────────────────────────────────
        self._cb5 = QCheckBox("הסרת רווחים ותווים מיותרים")
        self._cb5.setStyleSheet(_CB_STYLE)
        cl.addWidget(self._cb5)

        self._cb6 = QCheckBox("תיקון אוטומטי לפי מטא-דאטה")
        self._cb6.setStyleSheet(_CB_STYLE)
        cl.addWidget(self._cb6)

        # ── Separator ─────────────────────────────────────────────────────
        hr = QFrame()
        hr.setFrameShape(QFrame.Shape.HLine)
        hr.setStyleSheet("border: none; background: #c3d5ee; max-height: 1px;")
        cl.addWidget(hr)

        # ── Scope selector ────────────────────────────────────────────────
        scope_row = QHBoxLayout()
        scope_row.setSpacing(16)
        scope_lbl = QLabel("תחום:")
        scope_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: #2c4a6e; border: none;"
        )
        self._scope_grp = QButtonGroup(self)
        self._scope_main = QRadioButton("תיקייה ראשית בלבד")
        self._scope_sub  = QRadioButton("כולל תתי-תיקיות")
        self._scope_main.setChecked(True)
        for rb in (self._scope_main, self._scope_sub):
            rb.setStyleSheet("font-size: 14px; color: #333;")
            self._scope_grp.addButton(rb)
        scope_row.addWidget(scope_lbl)
        scope_row.addWidget(self._scope_main)
        scope_row.addWidget(self._scope_sub)
        scope_row.addStretch()
        cl.addLayout(scope_row)

        # ── Execute button ─────────────────────────────────────────────────
        exec_row = QHBoxLayout()
        exec_row.addStretch()
        self._exec_btn = QPushButton("בצע")
        self._exec_btn.setStyleSheet(_BTN_PRIMARY)
        self._exec_btn.clicked.connect(self._execute)
        exec_row.addWidget(self._exec_btn)
        cl.addLayout(exec_row)

        cards_row.addWidget(card, 2)

        tools_card = QFrame()
        tools_card.setStyleSheet("""
            QFrame {
                background: #f0f5fb;
                border: 1.5px solid #c3d5ee;
                border-radius: 12px;
            }
        """)
        tl = QVBoxLayout(tools_card)
        tl.setContentsMargins(20, 18, 20, 18)
        tl.setSpacing(10)

        tools_label = QLabel("כלים נוספים")
        tools_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #2c4a6e; border: none;"
        )
        tl.addWidget(tools_label)

        self._dup_signature_btn = QPushButton("מחיקת כפילויות לפי חתימה")
        self._dup_signature_btn.setStyleSheet(_BTN_PRIMARY)
        self._dup_signature_btn.clicked.connect(self._delete_duplicates_by_signature)
        tl.addWidget(self._dup_signature_btn)

        # ── "Empty source to target" button + options ─────────────────
        hr_tools1 = QFrame()
        hr_tools1.setFrameShape(QFrame.Shape.HLine)
        hr_tools1.setStyleSheet("border: none; background: #c3d5ee; max-height: 1px;")
        tl.addWidget(hr_tools1)

        self._move_to_target_btn = QPushButton("ריקון תיקיית מקור לתיקיית יעד")
        self._move_to_target_btn.setStyleSheet(_BTN_PRIMARY)
        self._move_to_target_btn.clicked.connect(self._move_source_to_target)
        tl.addWidget(self._move_to_target_btn)

        self._move_target_widget = QWidget()
        self._move_target_widget.setStyleSheet("QWidget { background: transparent; border: none; }")
        move_layout = QVBoxLayout(self._move_target_widget)
        move_layout.setContentsMargins(4, 2, 4, 2)
        move_layout.setSpacing(6)

        target_row = QHBoxLayout()
        target_row.setSpacing(8)
        target_lbl = QLabel("תיקיית יעד:")
        target_lbl.setStyleSheet(_LBL_SMALL)
        self._move_target_path = HebrewLineEdit()
        self._move_target_path.setPlaceholderText("הכנס נתיב יעד...")
        self._move_target_path.setStyleSheet(_INPUT_STYLE)
        self._move_target_browse_btn = QPushButton("עיון...")
        self._move_target_browse_btn.setStyleSheet("""
            QPushButton {background: #4682b4; color: #fff; border-radius: 6px; padding: 5px 12px; font-size:13px;}
            QPushButton:hover {background: #1e4972;}
        """)
        self._move_target_browse_btn.clicked.connect(self._browse_move_target)
        target_row.addWidget(target_lbl)
        target_row.addWidget(self._move_target_path, 1)
        target_row.addWidget(self._move_target_browse_btn)
        move_layout.addLayout(target_row)

        move_scope_row = QHBoxLayout()
        move_scope_row.setSpacing(12)
        self._move_scope_grp = QButtonGroup(self)
        self._move_scope_main = QRadioButton("תיקייה ראשית בלבד")
        self._move_scope_sub = QRadioButton("כולל תתי-תיקיות")
        self._move_scope_main.setChecked(True)
        for rb in (self._move_scope_main, self._move_scope_sub):
            rb.setStyleSheet("font-size: 13px; color: #333;")
            self._move_scope_grp.addButton(rb)
        move_scope_row.addWidget(self._move_scope_main)
        move_scope_row.addWidget(self._move_scope_sub)
        move_scope_row.addStretch()
        move_layout.addLayout(move_scope_row)

        self._move_exec_btn = QPushButton("העבר קבצים")
        self._move_exec_btn.setStyleSheet("""
            QPushButton {
                background: #2e86c1; color: #fff; border-radius: 8px;
                padding: 7px 24px; font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #1a5276; }
        """)
        self._move_exec_btn.clicked.connect(self._execute_move_source_to_target)
        move_layout.addWidget(self._move_exec_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._move_target_widget.setVisible(False)
        tl.addWidget(self._move_target_widget)

        # ── "Delete empty folders" button + options ───────────────────
        hr_tools2 = QFrame()
        hr_tools2.setFrameShape(QFrame.Shape.HLine)
        hr_tools2.setStyleSheet("border: none; background: #c3d5ee; max-height: 1px;")
        tl.addWidget(hr_tools2)

        self._del_empty_btn = QPushButton("מחיקת תיקיות ריקות")
        self._del_empty_btn.setStyleSheet(_BTN_PRIMARY)
        self._del_empty_btn.clicked.connect(self._delete_empty_folders)
        tl.addWidget(self._del_empty_btn)

        self._del_empty_widget = QWidget()
        self._del_empty_widget.setStyleSheet("QWidget { background: transparent; border: none; }")
        del_empty_layout = QVBoxLayout(self._del_empty_widget)
        del_empty_layout.setContentsMargins(4, 2, 4, 2)
        del_empty_layout.setSpacing(6)

        del_empty_scope_row = QHBoxLayout()
        del_empty_scope_row.setSpacing(12)
        self._del_empty_scope_grp = QButtonGroup(self)
        self._del_empty_scope_main = QRadioButton("תיקייה ראשית בלבד")
        self._del_empty_scope_sub = QRadioButton("כולל תתי-תיקיות")
        self._del_empty_scope_main.setChecked(True)
        for rb in (self._del_empty_scope_main, self._del_empty_scope_sub):
            rb.setStyleSheet("font-size: 13px; color: #333;")
            self._del_empty_scope_grp.addButton(rb)
        del_empty_scope_row.addWidget(self._del_empty_scope_main)
        del_empty_scope_row.addWidget(self._del_empty_scope_sub)
        del_empty_scope_row.addStretch()
        del_empty_layout.addLayout(del_empty_scope_row)

        self._del_empty_exec_btn = QPushButton("מחק תיקיות ריקות")
        self._del_empty_exec_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b; color: #fff; border-radius: 8px;
                padding: 7px 24px; font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #a93226; }
        """)
        self._del_empty_exec_btn.clicked.connect(self._execute_delete_empty_folders)
        del_empty_layout.addWidget(self._del_empty_exec_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._del_empty_widget.setVisible(False)
        tl.addWidget(self._del_empty_widget)

        # ── "Convert audio files" button + options ────────────────────
        hr_tools3 = QFrame()
        hr_tools3.setFrameShape(QFrame.Shape.HLine)
        hr_tools3.setStyleSheet("border: none; background: #c3d5ee; max-height: 1px;")
        tl.addWidget(hr_tools3)

        self._convert_btn = QPushButton("המרת קבצי שמע")
        self._convert_btn.setStyleSheet(_BTN_PRIMARY)
        self._convert_btn.clicked.connect(self._toggle_convert_panel)
        tl.addWidget(self._convert_btn)

        self._convert_widget = QWidget()
        self._convert_widget.setStyleSheet(
            "QWidget { background: #e8eef6; border: 1px solid #c3d5ee; border-radius: 8px; }"
        )
        convert_layout = QVBoxLayout(self._convert_widget)
        convert_layout.setContentsMargins(10, 8, 10, 8)
        convert_layout.setSpacing(6)

        # Source format
        src_fmt_row = QHBoxLayout()
        src_fmt_row.setSpacing(8)
        src_fmt_lbl = QLabel("פורמט מקור:")
        src_fmt_lbl.setStyleSheet(_LBL_SMALL)
        self._convert_src_fmt = QComboBox()
        self._convert_src_fmt.addItems(["mp3", "flac", "wav", "ogg", "m4a", "mp4", "aac", "opus", "aiff", "כל הפורמטים"])
        self._convert_src_fmt.setCurrentText("mp3")
        self._convert_src_fmt.setStyleSheet("font-size: 13px; padding: 3px 6px;")
        src_fmt_row.addWidget(src_fmt_lbl)
        src_fmt_row.addWidget(self._convert_src_fmt)
        src_fmt_row.addStretch()
        convert_layout.addLayout(src_fmt_row)

        # Target format
        tgt_fmt_row = QHBoxLayout()
        tgt_fmt_row.setSpacing(8)
        tgt_fmt_lbl = QLabel("פורמט יעד:")
        tgt_fmt_lbl.setStyleSheet(_LBL_SMALL)
        self._convert_tgt_fmt = QComboBox()
        self._convert_tgt_fmt.addItems(["mp3", "flac", "wav", "ogg", "m4a", "aac", "opus", "aiff"])
        self._convert_tgt_fmt.setCurrentText("flac")
        self._convert_tgt_fmt.setStyleSheet("font-size: 13px; padding: 3px 6px;")
        tgt_fmt_row.addWidget(tgt_fmt_lbl)
        tgt_fmt_row.addWidget(self._convert_tgt_fmt)
        tgt_fmt_row.addStretch()
        convert_layout.addLayout(tgt_fmt_row)

        # Bitrate (relevant for lossy formats)
        bitrate_row = QHBoxLayout()
        bitrate_row.setSpacing(8)
        bitrate_lbl = QLabel("ביטרייט (kbps, לפורמטים דחוסים):")
        bitrate_lbl.setStyleSheet(_LBL_SMALL)
        self._convert_bitrate = QComboBox()
        self._convert_bitrate.addItems(["אוטומטי", "128", "192", "256", "320"])
        self._convert_bitrate.setCurrentText("אוטומטי")
        self._convert_bitrate.setStyleSheet("font-size: 13px; padding: 3px 6px;")
        bitrate_row.addWidget(bitrate_lbl)
        bitrate_row.addWidget(self._convert_bitrate)
        bitrate_row.addStretch()
        convert_layout.addLayout(bitrate_row)

        # Scope
        convert_scope_row = QHBoxLayout()
        convert_scope_row.setSpacing(12)
        self._convert_scope_grp = QButtonGroup(self)
        self._convert_scope_main = QRadioButton("תיקייה ראשית בלבד")
        self._convert_scope_sub = QRadioButton("כולל תתי-תיקיות")
        self._convert_scope_main.setChecked(True)
        for rb in (self._convert_scope_main, self._convert_scope_sub):
            rb.setStyleSheet("font-size: 13px; color: #333;")
            self._convert_scope_grp.addButton(rb)
        convert_scope_row.addWidget(self._convert_scope_main)
        convert_scope_row.addWidget(self._convert_scope_sub)
        convert_scope_row.addStretch()
        convert_layout.addLayout(convert_scope_row)

        # Delete originals option
        self._convert_delete_orig = QCheckBox("מחק קבצי מקור לאחר המרה מוצלחת")
        self._convert_delete_orig.setStyleSheet("font-size: 13px; color: #333;")
        self._convert_delete_orig.setChecked(False)
        convert_layout.addWidget(self._convert_delete_orig)

        # Execute button
        self._convert_exec_btn = QPushButton("בצע המרה")
        self._convert_exec_btn.setStyleSheet("""
            QPushButton {
                background: #2e86c1; color: #fff; border-radius: 8px;
                padding: 7px 24px; font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #1a5276; }
        """)
        self._convert_exec_btn.clicked.connect(self._execute_convert_files)
        convert_layout.addWidget(self._convert_exec_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._convert_widget.setVisible(False)
        tl.addWidget(self._convert_widget)

        # ── "Replace image" button + options ──────────────────────────
        hr_tools4 = QFrame()
        hr_tools4.setFrameShape(QFrame.Shape.HLine)
        hr_tools4.setStyleSheet("border: none; background: #c3d5ee; max-height: 1px;")
        tl.addWidget(hr_tools4)

        self._replace_img_btn = QPushButton("החלפת תמונה לקובץ")
        self._replace_img_btn.setStyleSheet(_BTN_PRIMARY)
        self._replace_img_btn.clicked.connect(self._toggle_replace_img_panel)
        tl.addWidget(self._replace_img_btn)

        self._replace_img_widget = QWidget()
        self._replace_img_widget.setStyleSheet(
            "QWidget { background: #e8eef6; border: 1px solid #c3d5ee; border-radius: 8px; }"
        )
        replace_img_layout = QVBoxLayout(self._replace_img_widget)
        replace_img_layout.setContentsMargins(10, 8, 10, 8)
        replace_img_layout.setSpacing(6)

        # Song file selector
        song_row = QHBoxLayout()
        song_row.setSpacing(8)
        song_lbl = QLabel("קובץ שיר:")
        song_lbl.setStyleSheet(_LBL_SMALL)
        self._replace_img_song_path = HebrewLineEdit()
        self._replace_img_song_path.setPlaceholderText("בחר קובץ שמע...")
        self._replace_img_song_path.setStyleSheet(_INPUT_STYLE)
        self._replace_img_song_browse = QPushButton("עיון...")
        self._replace_img_song_browse.setStyleSheet("""
            QPushButton {background: #4682b4; color: #fff; border-radius: 6px; padding: 5px 12px; font-size:13px;}
            QPushButton:hover {background: #1e4972;}
        """)
        self._replace_img_song_browse.clicked.connect(self._browse_replace_img_song)
        song_row.addWidget(song_lbl)
        song_row.addWidget(self._replace_img_song_path, 1)
        song_row.addWidget(self._replace_img_song_browse)
        replace_img_layout.addLayout(song_row)

        # Image file selector
        img_row = QHBoxLayout()
        img_row.setSpacing(8)
        img_lbl = QLabel("קובץ תמונה:")
        img_lbl.setStyleSheet(_LBL_SMALL)
        self._replace_img_image_path = HebrewLineEdit()
        self._replace_img_image_path.setPlaceholderText("בחר תמונה...")
        self._replace_img_image_path.setStyleSheet(_INPUT_STYLE)
        self._replace_img_image_browse = QPushButton("עיון...")
        self._replace_img_image_browse.setStyleSheet("""
            QPushButton {background: #4682b4; color: #fff; border-radius: 6px; padding: 5px 12px; font-size:13px;}
            QPushButton:hover {background: #1e4972;}
        """)
        self._replace_img_image_browse.clicked.connect(self._browse_replace_img_image)
        img_row.addWidget(img_lbl)
        img_row.addWidget(self._replace_img_image_path, 1)
        img_row.addWidget(self._replace_img_image_browse)
        replace_img_layout.addLayout(img_row)

        # Image preview label
        self._replace_img_preview = QLabel()
        self._replace_img_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._replace_img_preview.setFixedHeight(140)
        self._replace_img_preview.setStyleSheet("background: transparent; border: none;")
        replace_img_layout.addWidget(self._replace_img_preview)

        # Execute button
        self._replace_img_exec_btn = QPushButton("החלף תמונה")
        self._replace_img_exec_btn.setStyleSheet("""
            QPushButton {
                background: #2e86c1; color: #fff; border-radius: 8px;
                padding: 7px 24px; font-size: 14px; font-weight: 600;
            }
            QPushButton:hover { background: #1a5276; }
        """)
        self._replace_img_exec_btn.clicked.connect(self._execute_replace_image)
        replace_img_layout.addWidget(self._replace_img_exec_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._replace_img_widget.setVisible(False)
        tl.addWidget(self._replace_img_widget)

        tl.addStretch()

        cards_row.addWidget(tools_card, 1)

        root.addLayout(cards_row)
        root.addStretch()

    # =========================================================================
    # Helpers
    # =========================================================================

    def _get_folder(self) -> str:
        w = self.window()
        return w.folder_selector.current_folder if hasattr(w, "folder_selector") else ""

    def _list_audio_files(self, folder: str) -> list[Path]:
        if not folder or not os.path.isdir(folder):
            return []
        if self._scope_sub.isChecked():
            result: list[Path] = []
            for dirpath, _, filenames in os.walk(folder):
                for fname in filenames:
                    p = Path(dirpath) / fname
                    if p.suffix.lower() in AUDIO_EXTENSIONS:
                        result.append(p)
            return result
        return [
            p for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        ]

    def _read_metadata_artists(self, path: Path) -> list[str]:
        """Return list of artist names from the file's metadata (cached per run)."""
        if path in self._metadata_cache:
            return self._metadata_cache[path]
        if MutagenFile is None:
            result: list[str] = []
        else:
            try:
                audio = MutagenFile(str(path), easy=True)
                if audio is None:
                    result = []
                else:
                    result = [str(v) for v in audio.get("artist", [])]
            except Exception:
                result = []
        self._metadata_cache[path] = result
        return result

    def _read_metadata_title(self, path: Path) -> str:
        """Return the title tag from the file's metadata, or ''."""
        if MutagenFile is None:
            return ""
        try:
            audio = MutagenFile(str(path), easy=True)
            if audio is None:
                return ""
            titles = audio.get("title", [])
            return str(titles[0]) if titles else ""
        except Exception:
            return ""

    # =========================================================================
    # Option 1 – Remove artist name
    # =========================================================================

    @staticmethod
    def _clean_after_removal(stem: str) -> str:
        """Remove orphaned separators left after an artist name was deleted."""
        stem = _RE_DOUBLE_SPACE.sub(" ", stem)
        # Collapse multiple dashes/underscores/pipes (possibly with spaces) to " - "
        stem = re.sub(r"\s*[-–—_|]{2,}\s*", " - ", stem)
        # Remove empty parentheses and brackets
        stem = re.sub(r"\(\s*\)", "", stem)
        stem = re.sub(r"\[\s*\]", "", stem)
        # Strip leading/trailing separators and spaces
        stem = re.sub(r"^[\s\-–—_|,]+", "", stem)
        stem = re.sub(r"[\s\-–—_|,]+$", "", stem)
        stem = _RE_DOUBLE_SPACE.sub(" ", stem)
        return stem.strip()

    @staticmethod
    def _make_artist_pattern(artist_lower: str) -> str:
        """
        Build a regex pattern for *artist_lower* that also matches when spaces
        in the artist name are replaced by _, -, or – in the filename.
        E.g. "חיים ישראל" → matches "חיים ישראל", "חיים_ישראל", "חיים-ישראל", "חיים–ישראל".
        """
        parts = artist_lower.split(" ")
        if len(parts) == 1:
            return re.escape(parts[0])
        sep = r"[_ \-–]+"  # underscore, space, hyphen-minus (U+002D), or en-dash (U+2013)
        return sep.join(re.escape(p) for p in parts)

    def _remove_one_artist(self, stem: str, artist: str) -> str:
        """Remove *artist* (and an optional leading ו conjunction) from *stem*.
        Spaces in the artist name also match _, -, or – in the stem."""
        artist_pat = self._make_artist_pattern(artist.lower())
        # Match "ו<artist>" where the ו is not preceded by a Hebrew/English letter
        # (i.e. it is a standalone conjunction), OR just <artist>.
        # Both alternatives use word-boundary lookarounds for Hebrew and Latin.
        pattern = (
            rf"{_WB_BEFORE}ו{artist_pat}{_WB_AFTER}"
            rf"|{_WB_BEFORE}{artist_pat}{_WB_AFTER}"
        )
        new_stem = re.sub(pattern, "", stem, count=1, flags=re.IGNORECASE)
        return self._clean_after_removal(new_stem)

    def _get_artists_in_filename(self, f: Path) -> list[str]:
        """
        Return artist names (from 3 sources) that actually appear in the
        file's stem, preserving the order of discovery.
        Spaces in artist names also match _, -, or – in the filename.
        """
        stem_lower = f.stem.lower()
        found: list[str] = []
        seen: set[str] = set()

        def _add(artist: str) -> None:
            if not artist:
                return
            low = artist.lower()
            if low not in seen:
                artist_pat = self._make_artist_pattern(low)
                pattern = re.compile(
                    _WB_BEFORE + artist_pat + _WB_AFTER,
                    re.IGNORECASE,
                )
                if pattern.search(stem_lower):
                    found.append(artist)
                    seen.add(low)

        # Source 1 – metadata
        for a in self._read_metadata_artists(f):
            _add(a)

        # Source 2 – artists_tab list (sorted longest first to prefer greedy match)
        if self._artists_tab is not None:
            for a in sorted(getattr(self._artists_tab, "_artists_set", set()), key=len, reverse=True):
                _add(a)

        # Source 2b – aliases
        if self._artists_tab is not None:
            aliases_map = getattr(self._artists_tab, "_aliases_map", {})
            for _owner, aliases in aliases_map.items():
                for alias in aliases:
                    _add(alias)

        # Source 3 – folder name
        _add(f.parent.name)

        return found

    def _apply_remove_artist(self, files: list[Path]) -> tuple[list[tuple[Path, Path]], list[str]]:
        # First pass: collect artists per file
        file_artists: dict[Path, list[str]] = {}
        for f in files:
            artists: list[str] = []
            seen: set[str] = set()
            for artist in self._read_metadata_artists(f):
                if not artist:
                    continue
                artist_lower = artist.lower()
                if artist_lower in seen:
                    continue
                artist_pat = self._make_artist_pattern(artist_lower)
                pattern = re.compile(
                    _WB_BEFORE + artist_pat + _WB_AFTER,
                    re.IGNORECASE,
                )
                if pattern.search(f.stem):
                    artists.append(artist)
                    seen.add(artist_lower)
            if artists:
                file_artists[f] = artists

        # Ask ONE global question if any file has multiple artist names
        multi_files = {f for f, al in file_artists.items() if len(al) > 1}
        delete_all_multi = True
        if multi_files:
            mb = QMessageBox(self)
            mb.setWindowTitle("כמה שמות אמנים")
            mb.setText(
                f"נמצאו {len(multi_files)} קבצים עם כמה שמות אמנים בשם הקובץ.\n"
                "מה לעשות?"
            )
            del_btn  = mb.addButton("מחק את כולם",                 QMessageBox.ButtonRole.YesRole)
            mb.addButton("השאר את כולם (דלג על קבצים אלו)", QMessageBox.ButtonRole.NoRole)
            mb.exec()
            delete_all_multi = mb.clickedButton() == del_btn

        pairs: list[tuple[Path, Path]] = []
        skipped_empty: list[str] = []
        for f, artists in file_artists.items():
            if len(artists) > 1 and not delete_all_multi:
                continue
            stem = f.stem
            for artist in artists:
                stem = self._remove_one_artist(stem, artist)
            if not stem:
                skipped_empty.append(f.name)
                continue
            new_name = stem + f.suffix
            if new_name != f.name:
                pairs.append((f, f.parent / new_name))
        return pairs, skipped_empty

    @staticmethod
    def _sha256_file(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(_HASH_CHUNK_SIZE), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _sha256_audio_without_edge_silence(path: Path) -> str:
        if AudioSegment is None or detect_leading_silence is None:
            raise OSError("חסרה הספרייה pydub")

        try:
            audio = AudioSegment.from_file(str(path))
        except Exception as e:
            raise OSError(str(e))

        if len(audio) == 0:
            return hashlib.sha256(b"").hexdigest()

        silence_thresh = (
            _SILENCE_DBFS_FOR_SILENT
            if audio.dBFS == float("-inf")
            else audio.dBFS - _SILENCE_DBFS_OFFSET
        )
        start_trim = detect_leading_silence(
            audio,
            silence_threshold=silence_thresh,
            chunk_size=_SILENCE_CHUNK_MS,
        )
        end_trim = detect_leading_silence(
            audio.reverse(),
            silence_threshold=silence_thresh,
            chunk_size=_SILENCE_CHUNK_MS,
        )
        end_index = len(audio) - end_trim
        if start_trim >= end_index:
            trimmed = audio[0:0]
        else:
            trimmed = audio[start_trim:end_index]

        if len(trimmed) == 0:
            payload = b""
        else:
            sample_length_ms = max(1, math.ceil(len(trimmed) * _AUDIO_SIGNATURE_SAMPLE_RATIO))
            sampled = trimmed[:sample_length_ms]
            payload = (
                f"{sampled.frame_rate}|{sampled.channels}|{sampled.sample_width}|".encode("utf-8")
                + sampled.raw_data
            )
        return hashlib.sha256(payload).hexdigest()

    def _extract_album_art_pixmap(self, path: Path) -> QPixmap | None:
        if MutagenFile is None:
            return None
        try:
            audio = MutagenFile(str(path))
        except Exception:
            return None
        if audio is None:
            return None

        image_data = None
        tags = getattr(audio, "tags", None)

        if tags is not None and hasattr(tags, "getall"):
            try:
                apic_list = tags.getall("APIC")
                if apic_list:
                    image_data = getattr(apic_list[0], "data", None)
            except Exception:
                image_data = None

        if image_data is None and hasattr(audio, "pictures"):
            try:
                pics = getattr(audio, "pictures", [])
                if pics:
                    image_data = getattr(pics[0], "data", None)
            except Exception:
                image_data = None

        # OGG / OPUS – metadata_block_picture (base64-encoded FLAC Picture)
        if image_data is None and tags is not None and hasattr(tags, "get"):
            try:
                import base64 as _b64
                from mutagen.flac import Picture as _Picture
                mbp = tags.get("metadata_block_picture")
                if mbp:
                    pic = _Picture(_b64.b64decode(mbp[0]))
                    image_data = pic.data
            except Exception:
                pass

        if image_data is None and tags is not None and hasattr(tags, "get"):
            try:
                covr = tags.get("covr")
                if covr:
                    image_data = bytes(covr[0])
            except Exception:
                image_data = None

        if not image_data:
            return None

        pixmap = QPixmap()
        if not pixmap.loadFromData(image_data):
            return None
        return pixmap

    @staticmethod
    def _should_process_progress_events(current: int, total: int) -> bool:
        return (current % _PROGRESS_EVENTS_STEP == 0) or (current == total)

    def _list_audio_files_recursive(self, folder: str) -> list[Path]:
        result: list[Path] = []
        for dirpath, _, filenames in os.walk(folder):
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix.lower() in AUDIO_EXTENSIONS:
                    result.append(p)
        return result

    def _list_audio_files_flat(self, folder: str) -> list[Path]:
        """List audio files in the given folder only (no subfolders)."""
        if not folder or not os.path.isdir(folder):
            return []
        return [
            p for p in Path(folder).iterdir()
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        ]

    def _delete_duplicates_by_signature(self) -> None:
        folder = self._get_folder()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "שגיאה", "יש לבחור תיקייה תחילה.")
            return

        # ── Ask user whether to include subfolders ─────────────────────
        scope_dlg = QMessageBox(self)
        scope_dlg.setWindowTitle("מחיקת כפילויות לפי חתימה")
        scope_dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        scope_dlg.setText("האם לכלול גם תתי-תיקיות בסריקה?")
        scope_dlg.setIcon(QMessageBox.Icon.Question)
        btn_with_sub = scope_dlg.addButton("כולל תתי-תיקיות", QMessageBox.ButtonRole.YesRole)
        btn_main_only = scope_dlg.addButton("תיקייה ראשית בלבד", QMessageBox.ButtonRole.NoRole)
        scope_dlg.addButton("ביטול", QMessageBox.ButtonRole.RejectRole)
        scope_dlg.exec()
        clicked = scope_dlg.clickedButton()
        if clicked is btn_with_sub:
            files = self._list_audio_files_recursive(folder)
        elif clicked is btn_main_only:
            files = self._list_audio_files_flat(folder)
        else:
            return
        if not files:
            QMessageBox.information(self, "אין קבצים", "לא נמצאו קבצי שמע בתיקייה.")
            return
        if AudioSegment is None or detect_leading_silence is None:
            QMessageBox.warning(
                self,
                "חסרה ספרייה",
                "כדי למחוק כפילויות לפי חתימה עם חיתוך שקט צריך להתקין pydub:\n\npip install pydub",
            )
            return

        groups: dict[str, list[Path]] = {}
        errors: list[str] = []
        total_files = len(files)
        progress = QProgressDialog("סורק קבצים לחתימה...", "ביטול", 0, total_files, self)
        progress.setWindowTitle("מחיקת כפילויות לפי חתימה")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        for idx, f in enumerate(files, start=1):
            if progress.wasCanceled():
                progress.close()
                QMessageBox.information(self, "כפילויות", "הסריקה בוטלה על ידי המשתמש.")
                return
            try:
                sig = self._sha256_audio_without_edge_silence(f)
            except OSError as e:
                errors.append(f"{f}: {e}")
            else:
                groups.setdefault(sig, []).append(f)
            progress.setValue(idx)
            if self._should_process_progress_events(idx, total_files):
                QApplication.processEvents()

        progress.close()

        duplicates = [sorted(paths, key=lambda p: p.as_posix()) for paths in groups.values() if len(paths) > 1]
        duplicates.sort(key=lambda paths: (-len(paths), paths[0].as_posix()))
        if not duplicates:
            msg = "לא נמצאו כפילויות לפי חתימה."
            if errors:
                msg += "\n\nשגיאות קריאה:\n" + "\n".join(errors[:_MAX_MSG_ITEMS])
            QMessageBox.information(self, "כפילויות", msg)
            return

        base_folder = Path(folder)

        dlg = QDialog(self)
        dlg.setWindowTitle("מחיקת כפילויות לפי חתימה")
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dlg.resize(960, 620)
        dlg.setStyleSheet("""
            QDialog { background: #f8fafd; }
            QScrollArea { border: none; background: transparent; }
        """)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # ── Header ─────────────────────────────────────────────────────
        header = QLabel("בחר שירים לשמירה בכל קבוצה — כל השאר יימחקו")
        header.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #1c355e; padding: 0 0 4px 0;"
        )
        layout.addWidget(header)

        total_dups = sum(len(p) - 1 for p in duplicates)
        summary_lbl = QLabel(
            f"נמצאו {len(duplicates)} קבוצות כפילויות  •  {total_dups} קבצים מיותרים"
        )
        summary_lbl.setStyleSheet("font-size: 13px; color: #5a6b85; padding: 0 0 6px 0;")
        layout.addWidget(summary_lbl)

        # ── Scroll area ────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(14)
        container_layout.setContentsMargins(0, 0, 8, 0)

        keep_choices: list[list[tuple[QCheckBox, Path]]] = []
        for idx, paths in enumerate(duplicates, start=1):
            # ── Group card ─────────────────────────────────────────────
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background: #ffffff;
                    border: 1px solid #d4dfe9;
                    border-radius: 10px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(10)

            group_label = QLabel(f"קבוצה {idx}  —  {len(paths)} עותקים זהים")
            group_label.setStyleSheet(
                "font-size: 14px; font-weight: 700; color: #2c4a6e; border: none;"
            )
            card_layout.addWidget(group_label)

            row_widget = QWidget()
            row_widget.setStyleSheet("border: none;")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setSpacing(18)
            row_layout.setContentsMargins(0, 0, 0, 0)

            cb_path_pairs: list[tuple[QCheckBox, Path]] = []
            # ברירת המחדל לשמירה: שם קובץ קצר ביותר, ואז שם (ללא תלות רישיות), ואז נתיב.
            keep_path = min(paths, key=lambda p: (len(p.name), p.name.casefold(), p.as_posix()))

            for p in paths:
                item_frame = QFrame()
                item_frame.setStyleSheet("""
                    QFrame {
                        background: #f5f8fc;
                        border: 1px solid #e0e8f0;
                        border-radius: 8px;
                    }
                    QFrame:hover {
                        background: #eaf0f8;
                        border-color: #a0b8d0;
                    }
                """)
                item_layout = QVBoxLayout(item_frame)
                item_layout.setSpacing(6)
                item_layout.setContentsMargins(10, 10, 10, 10)
                item_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

                art_label = QLabel("ללא\nתמונה")
                art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                art_label.setStyleSheet(
                    "font-size: 11px; color: #8a9bb5; border: 1px dashed #c3d5ee; "
                    f"border-radius: 6px; min-width: {_ALBUM_ART_SIZE}px; "
                    f"min-height: {_ALBUM_ART_SIZE}px; max-width: {_ALBUM_ART_SIZE}px; "
                    f"max-height: {_ALBUM_ART_SIZE}px; padding: 4px; background: #eef3fa;"
                )
                pixmap = self._extract_album_art_pixmap(p)
                if pixmap is not None:
                    art_label.setText("")
                    art_label.setPixmap(
                        pixmap.scaled(
                            _ALBUM_ART_SIZE,
                            _ALBUM_ART_SIZE,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    art_label.setStyleSheet(
                        f"border: 1px solid #c3d5ee; border-radius: 6px; "
                        f"max-width: {_ALBUM_ART_SIZE}px; max-height: {_ALBUM_ART_SIZE}px;"
                    )
                item_layout.addWidget(art_label, alignment=Qt.AlignmentFlag.AlignHCenter)

                cb = QCheckBox(p.name)
                cb.setToolTip(str(p))
                cb.setChecked(p == keep_path)
                cb.setStyleSheet(
                    "font-size: 13px; color: #1c355e; font-weight: 500; "
                    "border: none; padding: 2px 0;"
                )
                item_layout.addWidget(cb)

                # Show relative path from the base folder
                try:
                    rel = p.parent.relative_to(base_folder)
                    folder_text = str(rel) if str(rel) != "." else "תיקייה ראשית"
                except ValueError:
                    folder_text = str(p.parent)
                path_label = QLabel(f"📁 {folder_text}")
                path_label.setStyleSheet(
                    "font-size: 11px; color: #7a8da5; border: none; padding: 0;"
                )
                path_label.setToolTip(str(p.parent))
                item_layout.addWidget(path_label)

                row_layout.addWidget(item_frame)
                cb_path_pairs.append((cb, p))

            row_layout.addStretch()
            card_layout.addWidget(row_widget)
            container_layout.addWidget(card)
            keep_choices.append(cb_path_pairs)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        # ── Bottom buttons ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("ביטול")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #e8edf3; color: #3a4a60; border-radius: 8px;
                padding: 9px 30px; font-size: 14px; font-weight: 600;
                border: 1px solid #c3d5ee;
            }
            QPushButton:hover { background: #d5dde8; }
        """)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        delete_btn = QPushButton("🗑  מחק מסומנים")
        delete_btn.setStyleSheet("""
            QPushButton {
                background: #c0392b; color: #fff; border-radius: 8px;
                padding: 9px 30px; font-size: 14px; font-weight: 700;
            }
            QPushButton:hover { background: #a93226; }
        """)
        delete_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(delete_btn)

        layout.addLayout(btn_row)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        to_delete: list[Path] = []
        missing_selection = False
        for options in keep_choices:
            checked_any = any(cb.isChecked() for cb, _ in options)
            if not checked_any:
                missing_selection = True
                continue
            for cb, p in options:
                if not cb.isChecked():
                    to_delete.append(p)
        if missing_selection:
            QMessageBox.warning(self, "כפילויות", "יש לסמן לפחות שיר אחד לשמירה בכל קבוצה לפני מחיקה.")
            return

        if not to_delete:
            QMessageBox.information(self, "כפילויות", "לא נבחרו קבצים למחיקה.")
            return

        deleted = 0
        delete_errors: list[str] = []
        for p in to_delete:
            try:
                p.unlink()
                deleted += 1
            except OSError as e:
                delete_errors.append(f"{p}: {e}")

        summary = f"המחיקה הושלמה: נמחקו {deleted} מתוך {len(to_delete)} קבצים."
        if delete_errors:
            summary += "\n\nשגיאות מחיקה:\n" + "\n".join(delete_errors[:_MAX_MSG_ITEMS])
        if errors:
            summary += "\n\nשגיאות קריאה:\n" + "\n".join(errors[:_MAX_MSG_ITEMS])
        QMessageBox.information(self, "מחיקת כפילויות", summary)

    # =========================================================================
    # Move source folder contents to target folder
    # =========================================================================

    def _move_source_to_target(self) -> None:
        self._move_target_widget.setVisible(not self._move_target_widget.isVisible())

    def _browse_move_target(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "בחר תיקיית יעד")
        if folder:
            self._move_target_path.setText(folder)

    def _execute_move_source_to_target(self) -> None:
        source = self._get_folder()
        if not source or not os.path.isdir(source):
            QMessageBox.warning(self, "שגיאה", "יש לבחור תיקיית מקור תחילה.")
            return

        target = self._move_target_path.text().strip()
        if not target:
            QMessageBox.warning(self, "שגיאה", "יש להכניס נתיב תיקיית יעד.")
            return

        if not os.path.isdir(target):
            reply = QMessageBox.question(
                self, "תיקיית יעד",
                f"תיקיית היעד לא קיימת:\n{target}\n\nליצור אותה?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                os.makedirs(target, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(self, "שגיאה", f"לא ניתן ליצור את התיקייה:\n{e}")
                return

        include_sub = self._move_scope_sub.isChecked()
        if include_sub:
            files = self._list_audio_files_recursive(source)
        else:
            files = self._list_audio_files_flat(source)

        if not files:
            QMessageBox.information(self, "העברת קבצים", "לא נמצאו קבצי שמע בתיקיית המקור.")
            return

        confirm = QMessageBox.question(
            self, "העברת קבצים",
            f"להעביר {len(files)} קבצי שמע לתיקיית היעד?\n{target}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        moved = 0
        move_errors: list[str] = []
        for f in files:
            dest = Path(target) / f.name
            # Handle name collision
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                counter = 1
                while dest.exists() and counter < 10000:
                    dest = Path(target) / f"{stem} ({counter}){suffix}"
                    counter += 1
            try:
                shutil.move(str(f), str(dest))
                moved += 1
            except OSError as e:
                move_errors.append(f"{f.name}: {e}")

        summary = f"הושלם: הועברו {moved} מתוך {len(files)} קבצים."
        if move_errors:
            summary += "\n\nשגיאות:\n" + "\n".join(move_errors[:_MAX_MSG_ITEMS])
        QMessageBox.information(self, "העברת קבצים", summary)

    # =========================================================================
    # Delete empty folders
    # =========================================================================

    def _delete_empty_folders(self) -> None:
        self._del_empty_widget.setVisible(not self._del_empty_widget.isVisible())

    def _execute_delete_empty_folders(self) -> None:
        folder = self._get_folder()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "שגיאה", "יש לבחור תיקייה תחילה.")
            return

        include_sub = self._del_empty_scope_sub.isChecked()

        # First scan to show confirmation dialog
        empty_dirs = self._scan_empty_dirs(folder, include_sub)

        if not empty_dirs:
            QMessageBox.information(self, "תיקיות ריקות", "לא נמצאו תיקיות ריקות.")
            return

        confirm = QMessageBox.question(
            self, "מחיקת תיקיות ריקות",
            f"נמצאו {len(empty_dirs)} תיקיות ריקות. למחוק אותן?\n\n"
            "הפעולה תחזור על עצמה אוטומטית עד שלא יישארו תיקיות ריקות.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        total_deleted = 0
        all_errors: list[str] = []
        rounds = 0

        while empty_dirs:
            rounds += 1
            # Sort longest path first to delete deepest directories first
            for d in sorted(empty_dirs, key=len, reverse=True):
                try:
                    os.rmdir(d)
                    total_deleted += 1
                except OSError as e:
                    all_errors.append(f"{d}: {e}")

            # Re-scan for newly-empty parent directories
            empty_dirs = self._scan_empty_dirs(folder, include_sub)

        summary = f"הושלם: נמחקו {total_deleted} תיקיות ריקות"
        if rounds > 1:
            summary += f" ({rounds} סבבים)"
        summary += "."
        if all_errors:
            summary += "\n\nשגיאות:\n" + "\n".join(all_errors[:_MAX_MSG_ITEMS])
        QMessageBox.information(self, "מחיקת תיקיות ריקות", summary)

    def _scan_empty_dirs(self, folder: str, include_sub: bool) -> list[str]:
        empty_dirs: list[str] = []
        if include_sub:
            # Walk bottom-up so nested empty dirs are found after their children are removed
            for dirpath, _, _ in os.walk(folder, topdown=False):
                # Skip the root source folder itself
                if dirpath == folder:
                    continue
                if not os.listdir(dirpath):
                    empty_dirs.append(dirpath)
        else:
            # Only check immediate subdirectories
            try:
                for entry in os.scandir(folder):
                    if entry.is_dir(follow_symlinks=False):
                        if not os.listdir(entry.path):
                            empty_dirs.append(entry.path)
            except OSError:
                pass
        return empty_dirs

    # =========================================================================
    # Convert audio files
    # =========================================================================

    # Mapping from user-facing format name to pydub export format and extension
    _CONVERT_FORMAT_MAP: dict[str, tuple[str, str]] = {
        "mp3":  ("mp3",  ".mp3"),
        "flac": ("flac", ".flac"),
        "wav":  ("wav",  ".wav"),
        "ogg":  ("ogg",  ".ogg"),
        "m4a":  ("mp4",  ".m4a"),
        "mp4":  ("mp4",  ".mp4"),
        "aac":  ("adts", ".aac"),
        "opus": ("opus", ".opus"),
        "aiff": ("aiff", ".aiff"),
    }

    # Formats that benefit from a bitrate parameter (lossy codecs)
    _LOSSY_FORMATS = {"mp3", "ogg", "m4a", "aac", "opus"}

    def _toggle_convert_panel(self) -> None:
        self._convert_widget.setVisible(not self._convert_widget.isVisible())

    def _execute_convert_files(self) -> None:
        if AudioSegment is None:
            QMessageBox.warning(
                self, "חסרה ספרייה",
                "ספריית pydub אינה מותקנת.\n"
                "יש להתקין אותה עם: pip install pydub\n"
                "וכן להתקין FFmpeg במערכת.",
            )
            return

        folder = self._get_folder()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "שגיאה", "יש לבחור תיקייה תחילה.")
            return

        src_fmt_text = self._convert_src_fmt.currentText()
        tgt_fmt_text = self._convert_tgt_fmt.currentText()

        if src_fmt_text == tgt_fmt_text:
            QMessageBox.warning(self, "שגיאה", "פורמט המקור והיעד זהים.")
            return

        tgt_info = self._CONVERT_FORMAT_MAP.get(tgt_fmt_text)
        if tgt_info is None:
            QMessageBox.warning(self, "שגיאה", "פורמט יעד לא מוכר.")
            return
        tgt_pydub_fmt, tgt_ext = tgt_info

        # Determine source extensions to look for
        if src_fmt_text == "כל הפורמטים":
            src_extensions = set()
            for fmt_key, (_, ext) in self._CONVERT_FORMAT_MAP.items():
                if ext != tgt_ext:
                    src_extensions.add(ext)
        else:
            src_info = self._CONVERT_FORMAT_MAP.get(src_fmt_text)
            if src_info is None:
                QMessageBox.warning(self, "שגיאה", "פורמט מקור לא מוכר.")
                return
            src_extensions = {src_info[1]}

        include_sub = self._convert_scope_sub.isChecked()
        delete_originals = self._convert_delete_orig.isChecked()
        bitrate_text = self._convert_bitrate.currentText()
        bitrate = None if bitrate_text == "אוטומטי" else bitrate_text + "k"

        # Collect source files
        files = self._collect_files_for_conversion(folder, src_extensions, include_sub)
        if not files:
            QMessageBox.information(self, "אין קבצים", "לא נמצאו קבצים בפורמט המקור שנבחר.")
            return

        # Confirm
        bitrate_display = bitrate if bitrate else "אוטומטי"
        delete_note = "\nקבצי המקור יימחקו לאחר המרה מוצלחת." if delete_originals else ""
        reply = QMessageBox.question(
            self, "אישור המרה",
            f"נמצאו {len(files)} קבצים להמרה.\n"
            f"מקור: {src_fmt_text} → יעד: {tgt_fmt_text}\n"
            f"ביטרייט: {bitrate_display}{delete_note}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Progress dialog
        progress = QProgressDialog("מתחיל המרה...", "ביטול", 0, len(files), self)
        progress.setWindowTitle("המרת קבצי שמע")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        converted = 0
        errors: list[str] = []
        skipped: list[str] = []

        for i, src_path in enumerate(files):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            progress.setLabelText(f"ממיר: {src_path.name}  ({i + 1}/{len(files)})")
            QApplication.processEvents()

            tgt_path = src_path.with_suffix(tgt_ext)

            # Skip if the file is already in the target format
            if src_path.suffix.lower() == tgt_ext.lower():
                skipped.append(str(src_path.name))
                continue

            # Avoid overwriting existing files
            if tgt_path.exists():
                skipped.append(str(src_path.name))
                continue

            try:
                # Extract album art from source before conversion
                src_art_data, src_art_mime = self._extract_album_art_raw(src_path)

                audio = AudioSegment.from_file(str(src_path))
                export_params: dict = {"format": tgt_pydub_fmt}
                if tgt_fmt_text in self._LOSSY_FORMATS and bitrate is not None:
                    export_params["bitrate"] = bitrate
                audio.export(str(tgt_path), **export_params)

                # Re-embed album art into the converted file
                if src_art_data:
                    try:
                        self._embed_album_art(tgt_path, src_art_data, src_art_mime)
                    except Exception:
                        pass  # conversion succeeded even if art embedding fails

                converted += 1

                if delete_originals:
                    try:
                        src_path.unlink()
                    except OSError as e:
                        errors.append(f"מחיקת מקור נכשלה – {src_path.name}: {e}")

            except Exception as e:
                errors.append(f"{src_path.name}: {e}")

        progress.setValue(len(files))

        # Summary
        summary = f"הושלם: {converted} קבצים הומרו בהצלחה."
        if skipped:
            summary += (
                f"\n\n{len(skipped)} קבצים נדלגו (קובץ יעד כבר קיים):\n"
                + "\n".join(skipped[:_MAX_MSG_ITEMS])
            )
        if errors:
            summary += "\n\nשגיאות:\n" + "\n".join(errors[:_MAX_MSG_ITEMS])

        if errors:
            QMessageBox.warning(self, "המרה הושלמה עם שגיאות", summary)
        else:
            QMessageBox.information(self, "המרת קבצי שמע", summary)

    def _collect_files_for_conversion(
        self, folder: str, extensions: set[str], include_sub: bool,
    ) -> list[Path]:
        files: list[Path] = []
        if include_sub:
            for dirpath, _, filenames in os.walk(folder):
                for fn in filenames:
                    if Path(fn).suffix.lower() in extensions:
                        files.append(Path(dirpath) / fn)
        else:
            try:
                for entry in os.scandir(folder):
                    if entry.is_file(follow_symlinks=False):
                        if Path(entry.name).suffix.lower() in extensions:
                            files.append(Path(entry.path))
            except OSError:
                pass
        files.sort(key=lambda p: p.name.lower())
        return files

    # ── Album art helpers ─────────────────────────────────────────────────

    @staticmethod
    def _extract_album_art_raw(path: Path) -> tuple[bytes | None, str]:
        """Return (image_bytes, mime_type) from an audio file, or (None, '')."""
        if MutagenFile is None:
            return None, ""
        try:
            audio = MutagenFile(str(path))
        except Exception:
            return None, ""
        if audio is None:
            return None, ""

        tags = getattr(audio, "tags", None)

        # ID3 (MP3, AIFF, …)
        if tags is not None and hasattr(tags, "getall"):
            try:
                apic_list = tags.getall("APIC")
                if apic_list:
                    data = getattr(apic_list[0], "data", None)
                    mime = getattr(apic_list[0], "mime", "image/jpeg")
                    if data:
                        return bytes(data), mime
            except Exception:
                pass

        # FLAC / OGG Vorbis pictures
        if hasattr(audio, "pictures"):
            try:
                pics = getattr(audio, "pictures", [])
                if pics:
                    data = getattr(pics[0], "data", None)
                    mime = getattr(pics[0], "mime", "image/jpeg")
                    if data:
                        return bytes(data), mime
            except Exception:
                pass

        # OGG / OPUS – metadata_block_picture (base64-encoded FLAC Picture)
        if tags is not None and hasattr(tags, "get"):
            try:
                import base64 as _b64
                from mutagen.flac import Picture as _Picture
                mbp = tags.get("metadata_block_picture")
                if mbp:
                    pic = _Picture(_b64.b64decode(mbp[0]))
                    if pic.data:
                        return bytes(pic.data), (pic.mime or "image/jpeg")
            except Exception:
                pass

        # MP4 / M4A cover art
        if tags is not None and hasattr(tags, "get"):
            try:
                covr = tags.get("covr")
                if covr:
                    raw = bytes(covr[0])
                    fmt = getattr(covr[0], "imageformat", None)
                    # imageformat 14 == MP4Cover.FORMAT_PNG in mutagen.mp4
                    mime = "image/png" if fmt == 14 else "image/jpeg"
                    return raw, mime
            except Exception:
                pass

        return None, ""

    @staticmethod
    def _embed_album_art(path: Path, image_data: bytes, mime_type: str) -> None:
        """Embed album art into an audio file using mutagen.

        Raises ``RuntimeError`` for formats that do not support embedded art
        (e.g. WAV) so the caller can inform the user.
        """
        if MutagenFile is None:
            raise RuntimeError("ספריית mutagen אינה מותקנת.")

        ext = path.suffix.lower()

        if ext in (".mp3",):
            from mutagen.id3 import ID3, APIC, ID3NoHeaderError
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("APIC")
            tags.add(APIC(
                encoding=3,  # UTF-8
                mime=mime_type,
                type=3,  # Cover (front)
                desc="Cover",
                data=image_data,
            ))
            tags.save(str(path), v2_version=3)

        elif ext in (".flac",):
            from mutagen.flac import FLAC, Picture
            audio = FLAC(str(path))
            audio.clear_pictures()
            pic = Picture()
            pic.type = 3
            pic.mime = mime_type
            pic.desc = "Cover"
            pic.data = image_data
            audio.add_picture(pic)
            audio.save()

        elif ext in (".ogg", ".opus"):
            import base64
            from mutagen.oggvorbis import OggVorbis
            from mutagen.oggopus import OggOpus
            from mutagen.flac import Picture
            AudioClass = OggOpus if ext == ".opus" else OggVorbis
            audio = AudioClass(str(path))
            pic = Picture()
            pic.type = 3
            pic.mime = mime_type
            pic.desc = "Cover"
            pic.data = image_data
            encoded = base64.b64encode(pic.write()).decode("ascii")
            audio["metadata_block_picture"] = [encoded]
            audio.save()

        elif ext in (".m4a", ".mp4", ".aac"):
            from mutagen.mp4 import MP4, MP4Cover
            audio = MP4(str(path))
            if audio.tags is None:
                audio.add_tags()
            fmt = MP4Cover.FORMAT_PNG if "png" in mime_type else MP4Cover.FORMAT_JPEG
            audio.tags["covr"] = [MP4Cover(image_data, imageformat=fmt)]
            audio.save()

        elif ext in (".aiff", ".aif"):
            from mutagen.id3 import ID3, APIC, ID3NoHeaderError
            from mutagen.aiff import AIFF
            audio = AIFF(str(path))
            if audio.tags is None:
                audio.add_tags()
            audio.tags.delall("APIC")
            audio.tags.add(APIC(
                encoding=3,
                mime=mime_type,
                type=3,
                desc="Cover",
                data=image_data,
            ))
            audio.save()

        elif ext in (".wav",):
            raise RuntimeError(
                "פורמט WAV אינו תומך בהטמעת תמונת אלבום."
            )

        else:
            raise RuntimeError(
                f"פורמט {ext} אינו נתמך להטמעת תמונת אלבום."
            )

    # =========================================================================
    # Replace image for a file
    # =========================================================================

    def _toggle_replace_img_panel(self) -> None:
        self._replace_img_widget.setVisible(not self._replace_img_widget.isVisible())

    def _browse_replace_img_song(self) -> None:
        ext_list = " ".join(f"*{e}" for e in sorted(AUDIO_EXTENSIONS))
        path, _ = QFileDialog.getOpenFileName(
            self, "בחר קובץ שמע", "", f"קבצי שמע ({ext_list});;כל הקבצים (*)",
        )
        if path:
            self._replace_img_song_path.setText(path)

    def _browse_replace_img_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "בחר תמונה", "",
            "קבצי תמונה (*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tiff *.tif);;כל הקבצים (*)",
        )
        if path:
            self._replace_img_image_path.setText(path)
            # Show preview
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    130, 130,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._replace_img_preview.setPixmap(scaled)
            else:
                self._replace_img_preview.setText("לא ניתן לטעון תצוגה מקדימה")

    _COMPATIBLE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

    def _execute_replace_image(self) -> None:
        if MutagenFile is None:
            QMessageBox.warning(
                self, "חסרה ספרייה",
                "ספריית mutagen אינה מותקנת.\n"
                "יש להתקין אותה עם: pip install mutagen",
            )
            return

        song_path_str = self._replace_img_song_path.text().strip()
        image_path_str = self._replace_img_image_path.text().strip()

        if not song_path_str or not os.path.isfile(song_path_str):
            QMessageBox.warning(self, "שגיאה", "יש לבחור קובץ שמע תקין.")
            return

        if not image_path_str or not os.path.isfile(image_path_str):
            QMessageBox.warning(self, "שגיאה", "יש לבחור קובץ תמונה תקין.")
            return

        song_path = Path(song_path_str)
        image_path = Path(image_path_str)

        if song_path.suffix.lower() not in AUDIO_EXTENSIONS:
            QMessageBox.warning(self, "שגיאה", "הקובץ שנבחר אינו קובץ שמע מוכר.")
            return

        # Read image data – convert to JPEG in memory if not a compatible format
        img_ext = image_path.suffix.lower()
        if img_ext not in self._COMPATIBLE_IMAGE_EXTENSIONS:
            try:
                from PIL import Image as PILImage
            except ImportError:
                QMessageBox.warning(
                    self, "חסרה ספרייה",
                    "ספריית Pillow אינה מותקנת.\n"
                    "יש להתקין אותה עם: pip install Pillow\n"
                    "הספרייה נדרשת להמרת תמונות בפורמט לא נתמך.",
                )
                return

            try:
                import io as _io
                img = PILImage.open(str(image_path))
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")
                buf = _io.BytesIO()
                img.save(buf, "JPEG", quality=95)
                image_data = buf.getvalue()
                img_ext = ".jpg"
            except Exception as e:
                QMessageBox.warning(self, "שגיאת המרת תמונה", f"לא ניתן להמיר את התמונה:\n{e}")
                return
        else:
            try:
                image_data = image_path.read_bytes()
            except Exception as e:
                QMessageBox.warning(self, "שגיאה", f"לא ניתן לקרוא את קובץ התמונה:\n{e}")
                return

        mime_type = "image/png" if img_ext == ".png" else "image/jpeg"

        try:
            self._embed_album_art(song_path, image_data, mime_type)
        except Exception as e:
            QMessageBox.warning(self, "שגיאה", f"לא ניתן להחליף את התמונה:\n{e}")
            return

        # Verify the image was actually embedded by reading it back
        verify_data, _ = self._extract_album_art_raw(song_path)
        if not verify_data:
            QMessageBox.warning(
                self, "שגיאה",
                f"התמונה לא נשמרה בהצלחה בקובץ:\n{song_path.name}",
            )
            return

        QMessageBox.information(
            self, "החלפת תמונה",
            f"התמונה הוחלפה בהצלחה עבור:\n{song_path.name}",
        )

    # =========================================================================
    # Option 2 – Add artist name
    # =========================================================================

    def _apply_add_artist(self, files: list[Path]) -> list[tuple[Path, Path]]:
        if self._artists_tab is None:
            return []
        sep      = self._add_sep.text()
        at_start = self._add_start_rb.isChecked()
        pairs: list[tuple[Path, Path]] = []

        for f in files:
            raw_artists = self._read_metadata_artists(f)
            if not raw_artists:
                continue

            # Keep only artists whose every character is allowed
            valid: list[str] = []
            for a in raw_artists:
                if a and all(
                    self._artists_tab._is_allowed_artist_char(ch) for ch in a
                ):
                    valid.append(a)
            if not valid:
                continue

            # Prefer folder name when similar to the metadata artist
            folder_name = f.parent.name
            final: list[str] = []
            for part in valid:
                if folder_name and self._artists_tab._are_similar_artists(part, folder_name):
                    final.append(folder_name)
                else:
                    final.append(part)

            artist_str = ", ".join(final)
            stem       = f.stem

            # Artist already present → just fix spelling if needed
            idx = stem.lower().find(artist_str.lower())
            if idx != -1:
                actual = stem[idx: idx + len(artist_str)]
                if actual != artist_str:
                    new_stem = stem[:idx] + artist_str + stem[idx + len(artist_str):]
                    new_name = new_stem + f.suffix
                    if new_name != f.name:
                        pairs.append((f, f.parent / new_name))
                continue

            new_stem = (
                f"{artist_str}{sep}{stem}" if at_start
                else f"{stem}{sep}{artist_str}"
            )
            new_name = new_stem + f.suffix
            if new_name != f.name:
                pairs.append((f, f.parent / new_name))
        return pairs

    # =========================================================================
    # Option 3 – Delete individual characters
    # =========================================================================

    def _apply_delete_chars(self, files: list[Path]) -> list[tuple[Path, Path]]:
        chars = self._del_chars.text()
        if not chars:
            return []
        pairs: list[tuple[Path, Path]] = []
        for f in files:
            stem = f.stem
            for ch in chars:
                stem = stem.replace(ch, "")
            if not stem:
                continue
            new_name = stem + f.suffix
            if new_name != f.name:
                pairs.append((f, f.parent / new_name))
        return pairs

    # =========================================================================
    # Option 4 – Delete word / phrase (case-insensitive)
    # =========================================================================

    def _apply_delete_words(self, files: list[Path]) -> list[tuple[Path, Path]]:
        word = self._del_word.text()
        if not word:
            return []
        pattern = re.escape(word)
        pairs: list[tuple[Path, Path]] = []
        for f in files:
            new_stem = re.sub(pattern, "", f.stem, flags=re.IGNORECASE)
            if not new_stem.strip():
                continue
            new_name = new_stem + f.suffix
            if new_name != f.name:
                pairs.append((f, f.parent / new_name))
        return pairs

    # =========================================================================
    # Option 5 – Remove extra spaces / edge characters
    # =========================================================================

    @staticmethod
    def _clean_stem(stem: str) -> str:
        """
        Iteratively:
          1. Collapse double spaces to single space.
          2. Strip non-letter/non-apostrophe chars from the start.
          3. Strip non-letter/non-apostrophe chars from the end.
        Repeat until the stem is stable (at most 20 passes).
        """
        for _ in range(20):
            prev = stem
            stem = _RE_DOUBLE_SPACE.sub(" ", stem)
            stem = _RE_TRIM_START.sub("", stem)
            stem = _RE_TRIM_END.sub("", stem)
            if stem == prev:
                break
        return stem

    @staticmethod
    def _extract_leading_number(stem: str):
        """מחזיר (מחרוזת_קידומת, שאר) אם יש מספר בתחילת שם הקובץ, אחרת (None, None).
        הקידומת כוללת את המספר ונקודה אופציונלית (ללא רווח מאחור)."""
        m = re.match(r'^(\d+)(\.?)', stem)
        if m:
            prefix = m.group(1) + m.group(2)  # מספר + נקודה אופציונלית
            rest = stem[m.end():]              # מה שנשאר אחרי המספר (ונקודה)
            return prefix, rest
        return None, None

    @staticmethod
    def _clean_stem_preserve_numbers(stem: str) -> str:
        """כמו _clean_stem אך משמר מספר מוביל (ונקודה אחריו אם קיימת)."""
        prefix, rest = FeaturesTab._extract_leading_number(stem)
        if prefix is None:
            return FeaturesTab._clean_stem(stem)
        cleaned_rest = FeaturesTab._clean_stem(rest)
        if cleaned_rest:
            result = prefix + " " + cleaned_rest
            return _RE_DOUBLE_SPACE.sub(" ", result).strip()
        return prefix

    @staticmethod
    def _compute_preserve_number_folders(files: list[Path]) -> set[Path]:
        """מחזיר קבוצה של תיקיות שבהן יש לשמר מספרים מובילים.
        תנאים: לכל הקבצים בתיקייה יש מספר מוביל, ואין מספר שחוזר על עצמו
        (השוואה לפי ערך מספרי: 1 ו-11 נחשבים שונים, 01 ו-1 נחשבים זהים)."""
        from collections import defaultdict
        folder_files: dict[Path, list[Path]] = defaultdict(list)
        for f in files:
            folder_files[f.parent].append(f)

        preserve: set[Path] = set()
        for folder, folder_file_list in folder_files.items():
            seen_numbers: set[int] = set()
            all_have_numbers = True
            for f in folder_file_list:
                m = _RE_LEADING_NUMBER.match(f.stem)
                if m:
                    n = int(m.group(1))
                    if n in seen_numbers:  # מספר כפול — לא לשמר
                        all_have_numbers = False
                        break
                    seen_numbers.add(n)
                else:
                    all_have_numbers = False
                    break
            if all_have_numbers and seen_numbers:
                preserve.add(folder)
        return preserve

    def _apply_remove_extra(self, files: list[Path]) -> list[tuple[Path, Path]]:
        # שדרוג 5: שימור מספרים בתיקיות שכל שיריהן ממוספרים ייחודיים
        preserve_number_folders = self._compute_preserve_number_folders(files)

        pairs: list[tuple[Path, Path]] = []
        for f in files:
            if f.parent in preserve_number_folders:
                new_stem = self._clean_stem_preserve_numbers(f.stem)
            else:
                new_stem = self._clean_stem(f.stem)
            if not new_stem:
                continue
            new_name = new_stem + f.suffix
            if new_name != f.name:
                pairs.append((f, f.parent / new_name))
        return pairs

    # =========================================================================
    # Option 6 – Auto-fix from metadata title
    # =========================================================================

    @staticmethod
    def _has_irregular_chars(name: str) -> bool:
        """Return True if *name* contains characters outside the "normal" set."""
        common_punct = set(r".,;:'" + '"' + r"`-–—()[]{}_&+/\!?@#0123456789 ")
        for ch in name:
            if ch.isspace():
                continue
            is_heb = "\u05D0" <= ch <= "\u05EA"
            is_eng = ("A" <= ch <= "Z") or ("a" <= ch <= "z")
            is_pct = ch in common_punct
            if not (is_heb or is_eng or is_pct):
                return True
        return False

    def _apply_metadata_fix(self, files: list[Path]) -> list[tuple[Path, Path]]:
        pairs: list[tuple[Path, Path]] = []
        for f in files:
            title = self._read_metadata_title(f)
            if not title:
                continue

            if self._has_irregular_chars(title):
                mb = QMessageBox(self)
                mb.setWindowTitle("תווים לא רגילים")
                mb.setText(
                    f"השם מהמטא-דאטה מכיל תווים לא רגילים:\n{title}\n\nמה לעשות?"
                )
                use_btn  = mb.addButton("השתמש כמו שהוא", QMessageBox.ButtonRole.AcceptRole)
                skip_btn = mb.addButton("דלג",             QMessageBox.ButtonRole.RejectRole)
                fix_btn  = mb.addButton("תקן ידנית",       QMessageBox.ButtonRole.ActionRole)
                mb.exec()
                clicked = mb.clickedButton()
                if clicked == skip_btn:
                    continue
                if clicked == fix_btn:
                    new_title, ok = QInputDialog.getText(
                        self, "תיקון ידני", "ערוך את שם הקובץ:", text=title,
                    )
                    if not ok or not new_title.strip():
                        continue
                    title = new_title.strip()
                # else: use as-is

            # Sanitise for the filesystem (remove chars illegal in filenames)
            safe = re.sub(r'[\\/:*?"<>|]', "", title).strip()
            if not safe:
                continue
            new_name = safe + f.suffix
            if new_name != f.name:
                pairs.append((f, f.parent / new_name))
        return pairs

    # =========================================================================
    # Rename helper
    # =========================================================================

    @staticmethod
    def _do_rename(pairs: list[tuple[Path, Path]]) -> tuple[int, list[str]]:
        if not pairs:
            return 0, []

        # Preview dialog – show "before → after" and let user confirm
        preview_lines = [f"{src.name}  →  {dst.name}" for src, dst in pairs]
        dlg = QDialog()
        dlg.setWindowTitle("תצוגה מקדימה — שינויי שמות")
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dlg.resize(640, 420)
        layout = QVBoxLayout(dlg)
        lbl = QLabel(f"יבוצעו {len(pairs)} שינויים:")
        lbl.setStyleSheet("font-size: 14px; font-weight: 700;")
        layout.addWidget(lbl)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText("\n".join(preview_lines))
        txt.setStyleSheet("font-size: 13px;")
        layout.addWidget(txt)
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("בצע")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("בטל")
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return 0, []

        done   = 0
        errors: list[str] = []
        for src, dst in pairs:
            try:
                if dst.exists():
                    errors.append(f"קיים כבר: {dst.name}")
                    continue
                src.rename(dst)
                done += 1
            except OSError as e:
                errors.append(f"{src.name}: {e}")
        return done, errors

    # =========================================================================
    # Execute
    # =========================================================================

    def _execute(self) -> None:
        # Validate: at least one operation selected
        active = [
            cb for cb in (self._cb1, self._cb2, self._cb3,
                          self._cb4, self._cb5, self._cb6)
            if cb.isChecked()
        ]
        if not active:
            QMessageBox.warning(self, "לא נבחרו פעולות", "יש לסמן לפחות פעולה אחת.")
            return

        folder = self._get_folder()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "שגיאה", "יש לבחור תיקייה תחילה.")
            return

        files = self._list_audio_files(folder)
        if not files:
            QMessageBox.information(self, "אין קבצים", "לא נמצאו קבצי שמע בתיקייה.")
            return

        # Build confirmation text
        ops: list[str] = []
        if self._cb1.isChecked(): ops.append("הסרת שם האמן")
        if self._cb2.isChecked(): ops.append("הוספת שם אמן")
        if self._cb3.isChecked(): ops.append("מחיקת תווים")
        if self._cb4.isChecked(): ops.append("מחיקת מילים")
        if self._cb5.isChecked(): ops.append("הסרת רווחים ותווים מיותרים")
        if self._cb6.isChecked(): ops.append("תיקון לפי מטא-דאטה")

        reply = QMessageBox.question(
            self, "אישור ביצוע",
            f"לבצע על {len(files)} קבצים:\n"
            + "\n".join(f"• {op}" for op in ops) + "?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Reset per-run metadata cache
        self._metadata_cache = {}

        total_done  = 0
        all_errors: list[str] = []
        all_skipped_empty: list[str] = []

        def _step(apply_fn) -> None:
            nonlocal total_done
            current = self._list_audio_files(folder)
            result  = apply_fn(current)
            # _apply_remove_artist returns (pairs, skipped_empty); others return pairs
            if isinstance(result, tuple):
                pairs, skipped = result
                all_skipped_empty.extend(skipped)
            else:
                pairs = result
            done, errs = self._do_rename(pairs)
            total_done += done
            all_errors.extend(errs)

        # Execution order: 1 → 2 → 3 → 4 → 5 → 6
        if self._cb1.isChecked(): _step(self._apply_remove_artist)
        if self._cb2.isChecked(): _step(self._apply_add_artist)
        if self._cb3.isChecked(): _step(self._apply_delete_chars)
        if self._cb4.isChecked(): _step(self._apply_delete_words)
        if self._cb5.isChecked(): _step(self._apply_remove_extra)
        if self._cb6.isChecked(): _step(self._apply_metadata_fix)

        msg = f"הושלם: {total_done} קבצים שונו."
        if all_skipped_empty:
            msg += (
                f"\n\nאזהרה: {len(all_skipped_empty)} קבצים נדלגו כי שמם היה ריק לאחר המחיקה:\n"
                + "\n".join(all_skipped_empty[:_MAX_MSG_ITEMS])
            )
        if all_errors:
            QMessageBox.warning(
                self, "הושלם עם שגיאות",
                msg + "\n\nשגיאות:\n" + "\n".join(all_errors[:_MAX_MSG_ITEMS]),
            )
        else:
            QMessageBox.information(self, "הושלם", msg)
