import os
import re
import hashlib
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QMessageBox, QRadioButton, QButtonGroup,
    QFrame, QInputDialog, QDialog, QTextEdit, QDialogButtonBox, QScrollArea,
    QProgressDialog,
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
_DUP_SIGNATURE_DLG_SIZE = (860, 560)
_HASH_CHUNK_SIZE = 1024 * 1024

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

        silence_thresh = -50 if audio.dBFS == float("-inf") else audio.dBFS - 16
        start_trim = detect_leading_silence(audio, silence_thresh=silence_thresh, chunk_size=10)
        end_trim = detect_leading_silence(audio.reverse(), silence_thresh=silence_thresh, chunk_size=10)
        end_index = max(start_trim, len(audio) - end_trim)
        trimmed = audio[start_trim:end_index]

        if len(trimmed) == 0:
            payload = b""
        else:
            payload = (
                f"{trimmed.frame_rate}|{trimmed.channels}|{trimmed.sample_width}|".encode("utf-8")
                + trimmed.raw_data
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

    def _list_audio_files_recursive(self, folder: str) -> list[Path]:
        result: list[Path] = []
        for dirpath, _, filenames in os.walk(folder):
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix.lower() in AUDIO_EXTENSIONS:
                    result.append(p)
        return result

    def _delete_duplicates_by_signature(self) -> None:
        folder = self._get_folder()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "שגיאה", "יש לבחור תיקייה תחילה.")
            return

        files = self._list_audio_files_recursive(folder)
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
                progress.setValue(idx)
                QApplication.processEvents()
                continue
            groups.setdefault(sig, []).append(f)
            progress.setValue(idx)
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

        dlg = QDialog(self)
        dlg.setWindowTitle("מחיקת כפילויות לפי חתימה")
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dlg.resize(*_DUP_SIGNATURE_DLG_SIZE)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("בחר שיר לשמירה בכל קבוצה (כל השאר יסומנו למחיקה):"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(10)

        keep_choices: list[tuple[QButtonGroup, list[tuple[QRadioButton, Path]]]] = []
        for idx, paths in enumerate(duplicates, start=1):
            group_label = QLabel(f"קבוצה {idx} ({len(paths)} עותקים זהים):")
            group_label.setStyleSheet("font-weight: 700; color: #2c4a6e;")
            container_layout.addWidget(group_label)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setSpacing(16)
            row_layout.setContentsMargins(0, 0, 0, 0)

            group_radio = QButtonGroup(dlg)
            group_radio.setExclusive(True)
            radio_path_pairs: list[tuple[QRadioButton, Path]] = []
            keep_path = min(paths, key=lambda p: (len(p.name), p.name.casefold(), p.as_posix()))

            for p in paths:
                item_widget = QWidget()
                item_layout = QVBoxLayout(item_widget)
                item_layout.setSpacing(6)
                item_layout.setContentsMargins(0, 0, 0, 0)
                item_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

                art_label = QLabel("ללא תמונה")
                art_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                art_label.setStyleSheet(
                    "font-size: 12px; color: #5a6b85; border: 1px solid #c3d5ee; "
                    "border-radius: 6px; min-width: 130px; min-height: 130px; padding: 4px;"
                )
                pixmap = self._extract_album_art_pixmap(p)
                if pixmap is not None:
                    art_label.setPixmap(
                        pixmap.scaled(
                            130,
                            130,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                    art_label.setStyleSheet("border: 1px solid #c3d5ee; border-radius: 6px;")
                item_layout.addWidget(art_label)

                rb = QRadioButton(p.name)
                rb.setToolTip(str(p))
                rb.setChecked(p == keep_path)
                rb.setStyleSheet(_RB_STYLE)
                group_radio.addButton(rb)
                item_layout.addWidget(rb)
                row_layout.addWidget(item_widget)
                radio_path_pairs.append((rb, p))

            row_layout.addStretch()
            container_layout.addWidget(row_widget)
            keep_choices.append((group_radio, radio_path_pairs))

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("מחק מסומנים")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        to_delete: list[Path] = []
        for group_radio, options in keep_choices:
            keep_button = group_radio.checkedButton()
            if keep_button is None and options:
                keep_button = options[0][0]
            for rb, p in options:
                if rb is not keep_button:
                    to_delete.append(p)

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
