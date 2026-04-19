import os
import json
import traceback
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QDialogButtonBox, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSizePolicy, QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QTextEdit, QGroupBox, QCheckBox, QToolButton, QInputDialog,
    QDialog, QMessageBox, QRadioButton, QButtonGroup
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None

from shared import HebrewLineEdit, app_data_path


class AliasesDialog(QDialog):
    def __init__(self, parent: QWidget, artist_name: str, aliases: list[str]):
        super().__init__(parent)
        self.setWindowTitle(f"כינויים לאמן: {artist_name}")
        self.setMinimumSize(520, 420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._artist_name = artist_name

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel(f"כינויים עבור: {artist_name}")
        title.setStyleSheet("font-size: 18px; font-weight: 800; color: #1c355e;")
        root.addWidget(title)

        hint = QLabel("כל כינוי הוא שם חלופי. בהמשך, אם שם השיר תואם לכינוי — הוא יחשב כשייך לאמן הראשי.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #444;")
        root.addWidget(hint)

        self.listw = QListWidget()
        self.listw.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.listw.setStyleSheet("""
            QListWidget {
                border: 1px solid #d0d7e2;
                border-radius: 10px;
                background: #fbfcff;
                padding: 6px;
                font-size: 14px;
            }
            QListWidget::item { padding: 6px; border-radius: 8px; }
        """)
        root.addWidget(self.listw)

        for a in sorted(set(aliases)):
            item = QListWidgetItem(a)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.listw.addItem(item)

        add_box = QGroupBox("הוספת כינויים")
        add_box.setStyleSheet("""
            QGroupBox {
                font-weight: 700;
                border: 1px solid #d0d7e2;
                border-radius: 10px;
                margin-top: 8px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
        """)
        add_layout = QHBoxLayout(add_box)
        add_layout.setSpacing(10)

        self.add_edit = QLineEdit()
        self.add_edit.setPlaceholderText("כינוי חדש (או כמה כינויים מופרדים בפסיקים)...")
        self.add_edit.setStyleSheet("background:#fff; font-size:14px; padding:6px;")
        self.add_edit.returnPressed.connect(self._add_aliases)

        add_btn = QPushButton("הוסף")
        add_btn.setStyleSheet("""
            QPushButton {background: #4682b4; color: #fff; border-radius: 8px; padding: 8px 16px; font-size:14px; font-weight:700;}
            QPushButton:hover {background: #1e4972;}
        """)
        add_btn.clicked.connect(self._add_aliases)

        del_btn = QPushButton("מחק מסומנים")
        del_btn.setStyleSheet("""
            QPushButton {background: #d9534f; color: #fff; border-radius: 8px; padding: 8px 16px; font-size:14px; font-weight:800;}
            QPushButton:hover {background: #b63f3b;}
        """)
        del_btn.clicked.connect(self._delete_selected)

        add_layout.addWidget(self.add_edit, 1)
        add_layout.addWidget(add_btn)
        add_layout.addWidget(del_btn)

        root.addWidget(add_box)

        bottom = QHBoxLayout()
        bottom.addStretch()

        ok_btn = QPushButton("סגור")
        ok_btn.setStyleSheet("""
            QPushButton {background: #eef3f8; color: #1c355e; border: 1px solid #d0d7e2; border-radius: 8px; padding: 8px 16px; font-size:14px; font-weight:700;}
            QPushButton:hover {background: #dde7f2;}
        """)
        ok_btn.clicked.connect(self.accept)
        bottom.addWidget(ok_btn)

        root.addLayout(bottom)

    def _normalize(self, s: str) -> str:
        return " ".join(s.strip().split())

    def _add_aliases(self):
        raw = self.add_edit.text().strip()
        if not raw:
            return

        parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
        existing = {self.listw.item(i).text() for i in range(self.listw.count())}
        changed = False

        for p in parts:
            v = self._normalize(p)
            if not v:
                continue
            if v in existing:
                continue

            item = QListWidgetItem(v)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.listw.addItem(item)

            existing.add(v)
            changed = True

        if changed:
            self.add_edit.clear()

    def _delete_selected(self):
        for i in range(self.listw.count() - 1, -1, -1):
            item = self.listw.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.listw.takeItem(i)

    def get_aliases(self) -> list[str]:
        return [self.listw.item(i).text() for i in range(self.listw.count())]


class SplitArtistDialog(QDialog):
    def __init__(self, parent: QWidget, original_name: str, current_values: tuple[str, str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(f'פיצול אמן: {original_name}')
        self.setMinimumSize(460, 180)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel(f'יש להקליד שני שמות חדשים במקום "{original_name}"')
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #1c355e;")
        root.addWidget(title)

        self.name1_edit = QLineEdit()
        self.name2_edit = QLineEdit()

        if current_values:
            self.name1_edit.setText(current_values[0])
            self.name2_edit.setText(current_values[1])

        root.addWidget(self.name1_edit)
        root.addWidget(self.name2_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("אישור")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        buttons.accepted.connect(self._accept_form)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept_form(self):
        n1 = " ".join(self.name1_edit.text().strip().split())
        n2 = " ".join(self.name2_edit.text().strip().split())
        if not n1 or not n2:
            QMessageBox.warning(self, "שגיאה", "חובה למלא שני שמות.")
            return
        if n1 == n2:
            QMessageBox.warning(self, "שגיאה", "שני השמות חייבים להיות שונים.")
            return
        self.accept()

    def get_names(self) -> tuple[str, str]:
        return (
            " ".join(self.name1_edit.text().strip().split()),
            " ".join(self.name2_edit.text().strip().split()),
        )


class SimilarArtistsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        artists: list[str],
        split_candidates: dict[str, bool],
        split_suggestions: dict[str, tuple[str, str] | None],
    ):
        super().__init__(parent)
        self.setWindowTitle("השוואת אמנים דומים")
        self.setMinimumSize(860, 460)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._artists = artists
        self._split_candidates = split_candidates
        self._state: dict[str, str] = {name: "alias" for name in artists}
        self._main_artists: list[str] = []
        self._split_values: dict[str, tuple[str, str]] = {}
        self._rows: dict[str, dict[str, object]] = {}
        self._split_suggestions = split_suggestions

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("נמצאה קבוצת אמנים דומים. עבור כל אמן אפשר לבחור פעולה:")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #1c355e;")
        root.addWidget(title)

        hint = QLabel('ניתן לסמן עד שני אמנים כ-"אמן עיקרי". כל שאר האמנים באשכול שדומים לאמן עיקרי מסוים יוגדרו ככינויים שלו, מלבד אמנים שסומנו כ-"אל תכלול" או "פצל".')
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #555;")
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        grid.addWidget(QLabel("שם אמן"), 0, 0)
        grid.addWidget(QLabel("מצב"), 0, 1)
        grid.addWidget(QLabel("פעולות"), 0, 2)

        for i, name in enumerate(artists, start=1):
            name_lbl = QLabel(name)
            name_lbl.setStyleSheet("font-size: 14px; color: #1c355e; font-weight: 650;")

            status_lbl = QLabel("כינוי")
            status_lbl.setStyleSheet("font-size: 12px; color: #555;")

            actions = QWidget()
            actions_layout = QHBoxLayout(actions)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(6)

            main_btn = QPushButton("אמן עיקרי")
            alias_btn = QPushButton("הגדר ככינוי")
            ignore_btn = QPushButton("אל תכלול")
            split_btn = QPushButton("פצל")

            main_btn.clicked.connect(lambda _, n=name: self._set_main_artist(n))
            alias_btn.clicked.connect(lambda _, n=name: self._set_alias(n))
            ignore_btn.clicked.connect(lambda _, n=name: self._set_ignored(n))
            split_btn.clicked.connect(lambda _, n=name: self._set_split(n))

            main_btn.setStyleSheet("padding: 6px 10px;")
            alias_btn.setStyleSheet("padding: 6px 10px;")
            ignore_btn.setStyleSheet("padding: 6px 10px;")
            split_btn.setStyleSheet("padding: 6px 10px;")

            can_split = bool(split_candidates.get(name))
            split_btn.setEnabled(can_split)
            if not can_split:
                split_btn.setToolTip("פיצול זמין רק כשיש בשם הזה מילים נוספות לא תואמות מעבר לשתי מילים דומות")

            actions_layout.addWidget(main_btn)
            actions_layout.addWidget(alias_btn)
            actions_layout.addWidget(ignore_btn)
            actions_layout.addWidget(split_btn)

            grid.addWidget(name_lbl, i, 0)
            grid.addWidget(status_lbl, i, 1)
            grid.addWidget(actions, i, 2)

            self._rows[name] = {
                "status": status_lbl,
                "main_btn": main_btn,
                "alias_btn": alias_btn,
                "ignore_btn": ignore_btn,
                "split_btn": split_btn,
            }

        root.addLayout(grid)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("אישור")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_rows()

    def _set_main_artist(self, name: str):
        self._split_values.pop(name, None)

        if name in self._main_artists:
            # Toggle off: clicking again removes main status
            self._main_artists.remove(name)
            self._state[name] = "alias"
        elif len(self._main_artists) < 2:
            # Add as main artist (up to 2 allowed)
            self._main_artists.append(name)
            self._state[name] = "main"
        else:
            # Already 2 main artists – replace the first one
            old = self._main_artists.pop(0)
            self._state[old] = "alias"
            self._main_artists.append(name)
            self._state[name] = "main"

        # Reset non-main, non-ignored, non-split artists to alias
        for artist in self._artists:
            if artist in self._main_artists:
                continue
            if self._state.get(artist) in {"ignore", "split"}:
                continue
            self._state[artist] = "alias"

        self._refresh_rows()

    def _set_alias(self, name: str):
        if name in self._main_artists:
            self._main_artists.remove(name)
        self._split_values.pop(name, None)
        self._state[name] = "alias"
        self._refresh_rows()

    def _set_ignored(self, name: str):
        if name in self._main_artists:
            self._main_artists.remove(name)
        self._split_values.pop(name, None)
        self._state[name] = "ignore"
        self._refresh_rows()

    def _set_split(self, name: str):
        if not self._split_candidates.get(name):
            return

        initial_values = self._split_values.get(name) or self._split_suggestions.get(name)
        dlg = SplitArtistDialog(self, name, initial_values)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        if name in self._main_artists:
            self._main_artists.remove(name)

        self._split_values[name] = dlg.get_names()
        self._state[name] = "split"
        self._refresh_rows()

    def _refresh_rows(self):
        for name, row in self._rows.items():
            status_lbl: QLabel = row["status"]  # type: ignore[assignment]
            state = self._state.get(name, "alias")

            if state == "main":
                status_lbl.setText("אמן עיקרי")
                status_lbl.setStyleSheet("font-size: 12px; color: #1d7a35; font-weight: 700;")
            elif state == "ignore":
                status_lbl.setText("ללא שינוי / מוחרג")
                status_lbl.setStyleSheet("font-size: 12px; color: #8a6d3b; font-weight: 700;")
            elif state == "split":
                n1, n2 = self._split_values.get(name, ("", ""))
                status_lbl.setText(f'יפוצל ל: "{n1}" | "{n2}"')
                status_lbl.setStyleSheet("font-size: 12px; color: #8a4b08; font-weight: 700;")
            else:
                status_lbl.setText("כינוי")
                status_lbl.setStyleSheet("font-size: 12px; color: #555;")

    def get_selection(self) -> dict:
        return {
            "main_artist": self._main_artists[0] if len(self._main_artists) == 1 else None,
            "main_artists": list(self._main_artists),
            "ignored": [n for n, state in self._state.items() if state == "ignore"],
            "split_map": dict(self._split_values),
            "aliases": [n for n, state in self._state.items() if state == "alias"],
        }


class TwoArtistsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        a: str,
        b: str,
        reason: str | None,
        offer_split: bool,
        split_initial_values: tuple[str, str] | None = None,
        comparison_mode: str = "regular",
        primary_artist_name: str = "",
        alias_owner_name: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("השוואת אמנים דומים")
        self.setMinimumSize(640, 420)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self._a = a
        self._b = b
        self._reason = reason or ""
        self._comparison_mode = comparison_mode
        self._primary_artist_name = primary_artist_name
        self._alias_owner_name = alias_owner_name

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        if self._comparison_mode == "artist_vs_alias":
            title = QLabel(f'האם האמן "{self._primary_artist_name}" הוא כינוי לאמן "{self._alias_owner_name}"?')
            title.setStyleSheet("font-size: 16px; font-weight: 800; color: #1c355e;")
            title.setWordWrap(True)
            root.addWidget(title)
        else:
            title = QLabel("מי האמן המקורי?")
            title.setStyleSheet("font-size: 16px; font-weight: 800; color: #1c355e;")
            root.addWidget(title)

        if self._reason:
            reason_lbl = QLabel(f"סיבת הדמיון: {self._reason}")
            reason_lbl.setStyleSheet("font-size: 12px; color: #666;")
            reason_lbl.setWordWrap(True)
            root.addWidget(reason_lbl)

        self.group = QButtonGroup(self)
        self.rb_a = QRadioButton(a)
        self.rb_b = QRadioButton(b)
        self.rb_a.setChecked(True)
        self.group.addButton(self.rb_a)
        self.group.addButton(self.rb_b)

        self.rb_a.setStyleSheet("font-size: 14px; padding: 6px;")
        self.rb_b.setStyleSheet("font-size: 14px; padding: 6px;")

        if self._comparison_mode == "artist_vs_alias":
            self.rb_a.setText("כן")
            self.rb_b.setText("לא")

        root.addWidget(self.rb_a)
        root.addWidget(self.rb_b)

        self.ignore_checkbox = QCheckBox("לא לכלול יותר את הדמיון הזה (לא לשאול שוב על הצמד הזה)")
        self.ignore_checkbox.setStyleSheet("font-size: 13px; padding: 4px;")
        root.addWidget(self.ignore_checkbox)

        self.split_group = QGroupBox("פיצול לשני אמנים (רק כשיש מילים נוספות שלא תואמות)")
        self.split_group.setStyleSheet("QGroupBox { font-weight: 700; }")
        split_layout = QGridLayout(self.split_group)
        split_layout.setHorizontalSpacing(10)
        split_layout.setVerticalSpacing(8)

        self.split_checkbox = QCheckBox("אלו שני אמנים שונים (פיצול)")
        self.split_checkbox.setEnabled(bool(offer_split))
        self.split_checkbox.setChecked(False)
        split_layout.addWidget(self.split_checkbox, 0, 0, 1, 2)

        self.split_a_edit = QLineEdit()
        self.split_b_edit = QLineEdit()

        self.split_a_edit.setPlaceholderText("שם אמן מתוקן 1…")
        self.split_b_edit.setPlaceholderText("שם אמן מתוקן 2…")

        if split_initial_values:
            self.split_a_edit.setText(split_initial_values[0])
            self.split_b_edit.setText(split_initial_values[1])
        elif offer_split:
            self.split_a_edit.setText(self._a)
            self.split_b_edit.setText(self._b)

        self.split_a_edit.setEnabled(False)
        self.split_b_edit.setEnabled(False)

        split_layout.addWidget(self.split_a_edit, 1, 0)
        split_layout.addWidget(self.split_b_edit, 1, 1)

        split_hint = QLabel("בפיצול: יימחקו שני השמות הקודמים ויישארו רק שני השמות המתוקנים כאמנים נפרדים.")
        split_hint.setStyleSheet("font-size: 12px; color:#555;")
        split_hint.setWordWrap(True)
        split_layout.addWidget(split_hint, 2, 0, 1, 2)

        def on_split_changed(v: bool):
            self.split_a_edit.setEnabled(v)
            self.split_b_edit.setEnabled(v)
            self.fix_edit.setEnabled(not v)
            self.fix_edit.setPlaceholderText("מנוטרל בזמן פיצול" if v else "אם תרצה/י, כתוב/כתבי כאן שם אמן מתוקן חדש…")

        self.split_checkbox.toggled.connect(on_split_changed)
        root.addWidget(self.split_group)

        fix_box = QGroupBox("תיקון שם (אופציונלי)")
        fix_box.setStyleSheet("QGroupBox { font-weight: 700; }")
        fix_layout = QVBoxLayout(fix_box)

        self.fix_edit = QLineEdit()
        self.fix_edit.setPlaceholderText("אם תרצה/י, כתוב/כתבי כאן שם אמן מתוקן חדש…")
        self.fix_edit.setStyleSheet("background:#fff; font-size:13px; padding:6px;")
        fix_layout.addWidget(self.fix_edit)

        fix_hint = QLabel("אם ממלאים שם מתוקן: ייווצר אמן חדש בשם הזה, ושני השמות יהפכו לכינויים שלו.")
        fix_hint.setStyleSheet("font-size: 12px; color:#555;")
        fix_hint.setWordWrap(True)
        fix_layout.addWidget(fix_hint)

        root.addWidget(fix_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("אישור")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("ביטול")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def get_result(self) -> dict:
        chosen_original = self._a if self.rb_a.isChecked() else self._b
        return {
            "chosen_original": chosen_original,
            "ignore_pair": self.ignore_checkbox.isChecked(),
            "fix_name": self.fix_edit.text().strip(),
            "split_two_artists": self.split_checkbox.isChecked(),
            "split_name_a": self.split_a_edit.text().strip(),
            "split_name_b": self.split_b_edit.text().strip(),
        }


class ArtistRowWidget(QWidget):
    deleteRequested = pyqtSignal(str)
    editRequested = pyqtSignal(str)
    aliasesRequested = pyqtSignal(str)

    def __init__(self, artist_name: str):
        super().__init__()
        self.artist_name = artist_name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 10, 4)
        layout.setSpacing(6)

        self.checkbox = QCheckBox()
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setStyleSheet("""
            QCheckBox { background: transparent; border: none; padding: 0px; margin: 0px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)

        self.name_label = QLabel(f"  {artist_name}")
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.name_label.setStyleSheet("QLabel { font-size: 14px; color: #1c355e; font-weight: 650; }")

        def tool_btn(text: str, tooltip: str) -> QToolButton:
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tooltip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QToolButton {
                    border: 1px solid #d0d7e2;
                    background: #f6f8fb;
                    border-radius: 8px;
                    padding: 4px 8px;
                    font-size: 13px;
                    min-width: 28px;
                    min-height: 24px;
                }
                QToolButton:hover { background: #e7eef7; }
            """)
            return b

        self.aliases_btn = tool_btn("כינויים", "ניהול תת-שמות/כינויים לאמן")
        self.edit_btn = tool_btn("✎", "עריכת שם האמן")
        self.delete_btn = tool_btn("🗑", "מחיקת האמן")
        self.delete_btn.setStyleSheet(self.delete_btn.styleSheet() + "QToolButton:hover { background: #ffe5e5; }")

        self.aliases_btn.clicked.connect(lambda: self.aliasesRequested.emit(self.artist_name))
        self.edit_btn.clicked.connect(lambda: self.editRequested.emit(self.artist_name))
        self.delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self.artist_name))

        layout.addWidget(self.checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.name_label, 1, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.aliases_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.edit_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.delete_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.setStyleSheet("""
            QWidget {
                background: #ffffff;
                border: 1px solid #d7deea;
                border-radius: 10px;
            }
        """)


class ArtistsTab(QWidget):
    ARTISTS_FILE = "artists.txt"
    ALIASES_FILE = "artists_aliases.json"
    SIMILAR_IGNORE_FILE = "artists_similar_ignore.json"
    ENGLISH_HIDDEN_FILE = "artists_english_hidden.txt"
    ENGLISH_VISIBLE_FILE = "artists_english_visible.json"
    ENGLISH_HIDDEN_ALIASES_FILE = "artists_english_hidden_aliases.json"
    COMPARE_STAGE_ARTISTS_ONLY = 1
    COMPARE_STAGE_ARTISTS_TO_ALIASES_ONLY = 2
    COMPARE_STAGE_ALIASES_ONLY = 3

    def __init__(self, loading_progress_callback=None):
        super().__init__()
        self._artists_set: set[str] = set()
        self._artists_file_path = app_data_path(self.ARTISTS_FILE)
        self._aliases_file_path = app_data_path(self.ALIASES_FILE)
        self._similar_ignore_file_path = app_data_path(self.SIMILAR_IGNORE_FILE)
        self._english_hidden_file_path = app_data_path(self.ENGLISH_HIDDEN_FILE)
        self._english_visible_file_path = app_data_path(self.ENGLISH_VISIBLE_FILE)
        self._english_hidden_aliases_file_path = app_data_path(self.ENGLISH_HIDDEN_ALIASES_FILE)

        self._aliases_map: dict[str, list[str]] = {}
        self._similar_ignore_pairs: set[tuple[str, str]] = set()
        self._english_hidden_artists: set[str] = set()
        self._english_hidden_aliases_map: dict[str, list[str]] = {}
        self._english_artists_visible = True

        self._load_aliases_from_file()
        self._load_similar_ignore_pairs()
        self._load_english_hidden_artists()
        self._load_english_hidden_aliases_map()
        self._load_english_visibility_state()

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(10, 10, 10, 10)

        header = QLabel("רשימת אמנים")
        header.setStyleSheet("font-size: 22px; font-weight: 800; color: #1c355e;")
        root.addWidget(header)

        hint = QLabel("לכל אמן אפשר להגדיר כינויים (תת-שמות). בהמשך נשתמש בזה למיפוי שמות שירים.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#444; font-size: 13px;")
        root.addWidget(hint)

        content_row = QHBoxLayout()
        content_row.setSpacing(12)

        add_group = QGroupBox("הוספת אמנים")
        add_group.setStyleSheet(self._group_style())
        add_layout = QVBoxLayout(add_group)
        add_layout.setSpacing(8)
        add_layout.setContentsMargins(10, 12, 10, 10)

        quick_label = QLabel("הוספה מהירה")
        quick_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        quick_label.setStyleSheet("font-size:13px; font-weight:700; color:#1c355e;")

        self.single_edit = HebrewLineEdit()
        self.single_edit.setPlaceholderText("שם אמן (יחיד)...")
        self.single_edit.setStyleSheet("background:#fff; font-size:15px; padding:6px;")
        self.single_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.single_edit.returnPressed.connect(self.add_single_artist)

        self.add_single_btn = QPushButton("+")
        self.add_single_btn.setToolTip("הוסף אמן")
        self.add_single_btn.clicked.connect(self.add_single_artist)
        self.add_single_btn.setFixedWidth(42)
        self.add_single_btn.setStyleSheet("""
            QPushButton {background: #4682b4; color: #fff; border-radius: 8px; padding: 4px 0; font-size:22px; font-weight:900;}
            QPushButton:hover {background: #1e4972;}
            QPushButton:disabled {background: #9db5c8; color: #f3f3f3;}
        """)

        single_row = QHBoxLayout()
        single_row.setSpacing(8)
        single_row.addWidget(self.single_edit, 1)
        single_row.addWidget(self.add_single_btn, 0)

        multi_label = QLabel("הוספה מרובה")
        multi_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        multi_label.setStyleSheet("font-size:13px; font-weight:700; color:#1c355e;")

        self.multi_edit = QTextEdit()
        self.multi_edit.setPlaceholderText("הוספה מרובה: הדבק כאן כמה אמנים (כל שורה = אמן)")
        self.multi_edit.setStyleSheet("background:#fff; font-size:14px; padding:6px;")
        self.multi_edit.setFixedHeight(110)
        self.multi_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.add_multi_btn = QPushButton("+")
        self.add_multi_btn.setToolTip("הוסף רשימה")
        self.add_multi_btn.clicked.connect(self.add_multiple_artists)
        self.add_multi_btn.setFixedWidth(42)
        self.add_multi_btn.setStyleSheet("""
            QPushButton {background: #4682b4; color: #fff; border-radius: 8px; padding: 4px 0; font-size:22px; font-weight:900;}
            QPushButton:hover {background: #1e4972;}
            QPushButton:disabled {background: #9db5c8; color: #f3f3f3;}
        """)

        multi_row = QHBoxLayout()
        multi_row.setSpacing(8)
        multi_row.addWidget(self.multi_edit, 1)
        multi_row.addWidget(self.add_multi_btn, 0, Qt.AlignmentFlag.AlignTop)

        add_layout.addWidget(quick_label)
        add_layout.addLayout(single_row)
        add_layout.addSpacing(4)
        add_layout.addWidget(multi_label)
        add_layout.addLayout(multi_row)

        list_group = QGroupBox("האומנים בתוכנה")
        list_group.setStyleSheet(self._group_style())
        list_layout = QVBoxLayout(list_group)
        list_layout.setSpacing(12)

        self.search_edit = HebrewLineEdit()
        self.search_edit.setPlaceholderText("חיפוש אמן...")
        self.search_edit.setStyleSheet("background:#fff; font-size:14px; padding:6px;")
        self.search_edit.textChanged.connect(self.filter_artists_list)
        list_layout.addWidget(self.search_edit)

        self.artists_list = QListWidget()
        self.artists_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.artists_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #d0d7e2;
                border-radius: 10px;
                background: #fbfcff;
                padding: 4px;
            }
            QListWidget::item { border: none; }
        """)
        self.artists_list.setSpacing(1)
        self.artists_list.setMinimumHeight(260)
        self.artists_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        list_layout.addWidget(self.artists_list)

        actions_group = QGroupBox("פעולות")
        actions_group.setStyleSheet(self._group_style())
        actions_layout = QVBoxLayout(actions_group)
        actions_layout.setSpacing(10)

        self.delete_checked_btn = QPushButton("מחק מסומנים")
        self.delete_checked_btn.clicked.connect(self.delete_checked_artists)
        self.delete_checked_btn.setStyleSheet(self._danger_btn_style())

        self.check_all_btn = QPushButton("סמן הכל")
        self.check_all_btn.clicked.connect(self.check_all_artists)
        self.check_all_btn.setStyleSheet(self._secondary_btn_style())

        self.uncheck_all_btn = QPushButton("בטל סימון")
        self.uncheck_all_btn.clicked.connect(self.uncheck_all_artists)
        self.uncheck_all_btn.setStyleSheet(self._secondary_btn_style())

        self.similar_artists_btn = QPushButton("השוואת אמנים דומים")
        self.similar_artists_btn.clicked.connect(self.compare_similar_artists)
        self.similar_artists_btn.setStyleSheet(self._secondary_btn_style())

        self.import_artists_btn = QPushButton("ייבוא אמנים מהשירים בתיקייה")
        self.import_artists_btn.clicked.connect(self.import_artists_from_folder)
        self.import_artists_btn.setStyleSheet(self._secondary_btn_style())

        self.toggle_english_btn = QPushButton()
        self.toggle_english_btn.clicked.connect(self.toggle_english_artists_visibility)
        self.toggle_english_btn.setStyleSheet(self._secondary_btn_style())

        actions_layout.addWidget(self.toggle_english_btn)
        actions_layout.addWidget(self.delete_checked_btn)
        actions_layout.addWidget(self.check_all_btn)
        actions_layout.addWidget(self.uncheck_all_btn)
        actions_layout.addWidget(self.similar_artists_btn)
        actions_layout.addWidget(self.import_artists_btn)
        actions_layout.addStretch()

        side_col = QVBoxLayout()
        side_col.setSpacing(12)
        side_col.addWidget(add_group)
        side_col.addWidget(actions_group)
        side_col.addStretch()

        content_row.addWidget(list_group, 2)
        content_row.addLayout(side_col, 1)

        root.addLayout(content_row, 1)
        root.addStretch()

        self.load_artists_from_file(progress_callback=loading_progress_callback)

        if not self._english_artists_visible:
            self._apply_hidden_english_mode_on_startup()

        self._update_english_toggle_button_text()

    def _group_style(self) -> str:
        return """
            QGroupBox {
                font-weight: 700;
                border: 1px solid #d0d7e2;
                border-radius: 10px;
                margin-top: 8px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
        """

    def _secondary_btn_style(self) -> str:
        return """
            QPushButton {background: #eef3f8; color: #1c355e; border: 1px solid #d0d7e2; border-radius: 8px; padding: 8px 16px; font-size:15px; font-weight:700;}
            QPushButton:hover {background: #dde7f2;}
        """

    def _danger_btn_style(self) -> str:
        return """
            QPushButton {background: #d9534f; color: #fff; border-radius: 8px; padding: 8px 16px; font-size:15px; font-weight:800;}
            QPushButton:hover {background: #b63f3b;}
        """

    def _normalize_artist(self, name: str) -> str:
        s = name or ""
        for ch in [
            "\ufeff", "\u200b", "\u200c", "\u200d", "\u2060",
            "\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
        ]:
            s = s.replace(ch, "")
        return " ".join(s.strip().split())

    def _contains_supported_artist_letters(self, text: str) -> bool:
        return any(("א" <= ch <= "ת") or ("A" <= ch <= "Z") or ("a" <= ch <= "z") for ch in text)

    def _is_allowed_artist_char(self, ch: str) -> bool:
        return (
            ("א" <= ch <= "ת")
            or ("A" <= ch <= "Z")
            or ("a" <= ch <= "z")
            or ch.isspace()
            or ch in ".,;:'\"׳״`-–—()[]{}_&+/\\!?@"
        )

    def _sanitize_artist_name(self, name: str) -> str:
        cleaned = "".join(ch if self._is_allowed_artist_char(ch) else " " for ch in (name or ""))
        cleaned = self._normalize_artist(cleaned)
        if not cleaned or not self._contains_supported_artist_letters(cleaned):
            return ""
        return cleaned

    def _find_alias_owner(self, artist_name: str) -> str | None:
        artist_name = self._normalize_artist(artist_name)
        for artist, aliases in self._aliases_map.items():
            if artist_name in aliases:
                return artist
        return None

    def _get_owner_artist_for_name(self, name: str) -> str | None:
        name = self._normalize_artist(name)
        if not name:
            return None
        if name in self._artists_set:
            return name
        return self._find_alias_owner(name)

    def _get_all_comparable_names(self) -> list[str]:
        names = set(self._artists_set)
        for aliases in self._aliases_map.values():
            for alias in aliases:
                alias = self._normalize_artist(alias)
                if alias:
                    names.add(alias)
        return sorted(names)

    def _are_from_same_owner(self, a: str, b: str) -> bool:
        oa = self._get_owner_artist_for_name(a)
        ob = self._get_owner_artist_for_name(b)
        return bool(oa and ob and oa == ob)

    def _pair_key(self, a: str, b: str) -> tuple[str, str]:
        a = self._normalize_artist(a)
        b = self._normalize_artist(b)
        return (a, b) if a <= b else (b, a)

    def _remove_alias_from_owner(self, owner: str, alias: str):
        owner = self._normalize_artist(owner)
        alias = self._normalize_artist(alias)
        aliases = [a for a in self._aliases_map.get(owner, []) if self._normalize_artist(a) != alias]
        if aliases:
            self._aliases_map[owner] = sorted(set(aliases))
        else:
            self._aliases_map.pop(owner, None)

    def _remove_name_entity(self, name: str):
        name = self._normalize_artist(name)
        if not name:
            return

        alias_owner = self._find_alias_owner(name)
        if alias_owner:
            self._remove_alias_from_owner(alias_owner, name)
            self._save_aliases_to_file()
            return

        if name in self._artists_set:
            self._delete_artist_by_name_internal(name)

    def _split_result_already_resolved(self, name1: str, name2: str) -> bool:
        name1 = self._normalize_artist(name1)
        name2 = self._normalize_artist(name2)
        if not name1 or not name2 or name1 == name2:
            return False
        return name1 in self._artists_set and name2 in self._artists_set

    def _add_alias_to_artist(self, artist_name: str, alias_name: str):
        artist_name = self._normalize_artist(artist_name)
        alias_name = self._normalize_artist(alias_name)
        if not artist_name or not alias_name or artist_name == alias_name:
            return
        if artist_name not in self._artists_set:
            return

        aliases = self._aliases_map.get(artist_name, [])
        if alias_name not in aliases:
            aliases.append(alias_name)
        self._aliases_map[artist_name] = sorted(set(aliases))

    def _hide_english_artist_with_aliases(self, artist_name: str):
        artist_name = self._normalize_artist(artist_name)
        if not artist_name:
            return

        if artist_name not in self._artists_set:
            return

        self._english_hidden_artists.add(artist_name)

        aliases = self._aliases_map.pop(artist_name, [])
        normalized_aliases = sorted(
            set(
                self._normalize_artist(alias)
                for alias in aliases
                if self._normalize_artist(alias) and self._normalize_artist(alias) != artist_name
            )
        )

        if normalized_aliases:
            self._english_hidden_aliases_map[artist_name] = normalized_aliases
        else:
            self._english_hidden_aliases_map.pop(artist_name, None)

        self._artists_set.discard(artist_name) 

    def _restore_hidden_english_artist_with_aliases(self, artist_name: str):
        artist_name = self._normalize_artist(artist_name)
        if not artist_name:
            return

        self._english_hidden_artists.discard(artist_name)

        if artist_name not in self._artists_set:
            self._artists_set.add(artist_name)

        stored_aliases = self._english_hidden_aliases_map.pop(artist_name, [])
        valid_aliases: list[str] = []

        for alias in stored_aliases:
            alias = self._normalize_artist(alias)
            if not alias or alias == artist_name:
                continue

            if alias in self._artists_set:
                continue

            existing_owner = self._find_alias_owner(alias)
            if existing_owner and existing_owner != artist_name:
                continue

            valid_aliases.append(alias)

        if valid_aliases:
            current_aliases = self._aliases_map.get(artist_name, [])
            merged_aliases = sorted(set(current_aliases + valid_aliases))
            self._aliases_map[artist_name] = merged_aliases

    def _absorb_name_into_artist(self, target_name: str, source_name: str):
        target_artist = self._get_owner_artist_for_name(target_name) or self._normalize_artist(target_name)
        source_name = self._normalize_artist(source_name)

        if not target_artist or target_artist not in self._artists_set or not source_name:
            return
        if source_name == target_artist:
            return

        source_owner = self._get_owner_artist_for_name(source_name)
        if source_owner == target_artist:
            if source_name != target_artist:
                self._add_alias_to_artist(target_artist, source_name)
                old_owner = self._find_alias_owner(source_name)
                if old_owner and old_owner != target_artist:
                    self._remove_alias_from_owner(old_owner, source_name)
            return

        alias_owner = self._find_alias_owner(source_name)
        if alias_owner:
            self._remove_alias_from_owner(alias_owner, source_name)
            if source_name != target_artist:
                self._add_alias_to_artist(target_artist, source_name)
            self._save_aliases_to_file()
            return

        if source_name in self._artists_set:
            source_aliases = list(self._aliases_map.get(source_name, []))

            if source_name != target_artist:
                self._add_alias_to_artist(target_artist, source_name)

            for alias in source_aliases:
                alias = self._normalize_artist(alias)
                if alias and alias != target_artist:
                    self._add_alias_to_artist(target_artist, alias)

            self._delete_artist_by_name_internal(source_name)
            self._aliases_map.pop(source_name, None)
            self._save_aliases_to_file()
            self.save_artists_to_file()

    def _validate_artist_for_external_add(self, raw_name: str) -> tuple[str, str | None, str | None]:
        name = self._sanitize_artist_name(raw_name)
        if not name:
            return "", "invalid", None
        if name in self._artists_set or name in self._english_hidden_artists:
            return name, "artist_exists", None
        alias_owner = self._find_alias_owner(name)
        if alias_owner:
            return name, "alias_exists", alias_owner
        return name, None, None

    def _artist_add_error_message(self, artist_name: str, error_code: str, alias_owner: str | None = None) -> str:
        if error_code == "artist_exists":
            return f'האמן "{artist_name}" כבר קיים ברשימה.'
        if error_code == "alias_exists" and alias_owner:
            return f'האמן "{artist_name}" כבר קיים ככינוי לאמן "{alias_owner}".'
        return f'האמן "{artist_name}" לא נוסף כי שמו חייב להכיל אותיות בעברית או באנגלית בלבד.'
    
    def _promote_alias_to_artist(self, alias_name: str):
        alias_name = self._normalize_artist(alias_name)
        if not alias_name:
            return

        owner = self._find_alias_owner(alias_name)
        if owner:
            self._remove_alias_from_owner(owner, alias_name)

        if alias_name not in self._artists_set:
            self._add_artist_to_list(alias_name, persist=False)

        self._save_aliases_to_file()
        self.save_artists_to_file()

    def _match_split_target_name(self, candidate_name: str, split_names: tuple[str, str]) -> str | None:
        candidate_name = self._normalize_artist(candidate_name)
        if not candidate_name:
            return None

        n1 = self._normalize_artist(split_names[0] if len(split_names) > 0 else "")
        n2 = self._normalize_artist(split_names[1] if len(split_names) > 1 else "")

        options = [n for n in (n1, n2) if n]
        if not options:
            return None

        for option in options:
            if self._cmp_key(candidate_name) == self._cmp_key(option):
                return option

        similar_options = [option for option in options if self._are_similar_artists(candidate_name, option)]
        if len(similar_options) == 1:
            return similar_options[0]

        return None

    def _apply_split_to_cluster_entries(
        self,
        cluster_entries: list[dict[str, str]],
        normalized_split_map: dict[str, tuple[str, str]],
    ) -> set[str]:
        resolved_displays: set[str] = set()

        if not normalized_split_map:
            return resolved_displays

        entries_by_display = {entry["display"]: entry for entry in cluster_entries}

        for old_display, (name1, name2) in normalized_split_map.items():
            entry = entries_by_display.get(old_display)
            if not entry:
                continue

            old_name = entry["name"]
            self._remove_name_entity(old_name)
            self._add_artist_to_list(name1, persist=False)
            self._add_artist_to_list(name2, persist=False)
            resolved_displays.add(old_display)

        for display_name, entry in entries_by_display.items():
            if display_name in resolved_displays:
                continue

            candidate_name = self._normalize_artist(entry.get("name", ""))
            if not candidate_name:
                continue

            matched_target: str | None = None
            exact_match = False

            for split_names in normalized_split_map.values():
                target_name = self._match_split_target_name(candidate_name, split_names)
                if not target_name:
                    continue

                matched_target = target_name
                if self._cmp_key(candidate_name) == self._cmp_key(target_name):
                    exact_match = True
                break

            if not matched_target:
                continue

            if exact_match:
                self._remove_name_entity(candidate_name)
            else:
                self._absorb_name_into_artist(matched_target, candidate_name)

            resolved_displays.add(display_name)

        self._save_aliases_to_file()
        self.save_artists_to_file()
        return resolved_displays

    def _get_auto_resolved_cluster_displays_after_split(
        self,
        cluster_entries: list[dict[str, str]],
        normalized_split_map: dict[str, tuple[str, str]],
        ignored: list[str],
    ) -> set[str]:
        resolved_displays = set(ignored or [])
        resolved_displays.update(normalized_split_map.keys())

        if not normalized_split_map:
            return resolved_displays

        for entry in cluster_entries:
            display_name = entry["display"]
            if display_name in resolved_displays:
                continue

            candidate_name = self._normalize_artist(entry.get("name", ""))
            if not candidate_name:
                continue

            for split_names in normalized_split_map.values():
                target_name = self._match_split_target_name(candidate_name, split_names)
                if target_name:
                    resolved_displays.add(display_name)
                    break

        return resolved_displays

    def _cmp_key(self, name: str) -> str:
        s = self._normalize_artist(name)
        s = (
            s.replace("’", "'").replace("‘", "'").replace("‛", "'").replace("′", "'").replace("＇", "'")
             .replace("“", '"').replace("”", '"').replace("״", '"').replace("׳", "'")
             .replace("־", "-").replace("–", "-").replace("—", "-")
        )
        ignore_chars = {" ", "\t", ",", ".", "，", "-", "'", '"', "(", ")", "[", "]", "{", "}", ":", ";", "!", "?"}
        return "".join(ch for ch in s if ch not in ignore_chars)

    def _signature_letters(self, s: str) -> str:
        return "".join(sorted(s))

    def _strip_special_letters(self, s: str) -> str:
        return "".join(ch for ch in s if ch not in set("אוייהע"))

    def _is_distance_one(self, a: str, b: str) -> bool:
        if a == b:
            return False

        la, lb = len(a), len(b)

        if max(la, lb) <= 2:
            return False

        if abs(la - lb) > 1:
            return False

        if la == lb:
            return sum(1 for i in range(la) if a[i] != b[i]) == 1

        if la > lb:
            a, b = b, a
            la, lb = lb, la

        i = j = 0
        used_skip = False
        while i < la and j < lb:
            if a[i] == b[j]:
                i += 1
                j += 1
            else:
                if used_skip:
                    return False
                used_skip = True
                j += 1

        return True

    def _word_count_for_anagram_rule(self, raw_name: str) -> int:
        return len([w for w in raw_name.strip().split() if w])

    def _cmp_words(self, raw_name: str) -> list[str]:
        out: list[str] = []
        for w in [w for w in (raw_name or "").strip().split() if w]:
            cw = self._cmp_key(w)
            if cw:
                out.append(cw)
        return out

    def _is_generic_dj_word(self, word: str) -> bool:
        w = self._cmp_key(word).casefold()
        return w in {
            "dj",
            "deejay",
            "די",
            "גי",
            "גיי",
            "דיגי",
            "דיגיי",
        }

    def _are_similar_words(self, w1: str, w2: str) -> bool:
        if not w1 or not w2:
            return False

        if w1 == w2:
            return True

        if max(len(w1), len(w2)) <= 2:
            return False

        stripped_equal = self._strip_special_letters(w1) == self._strip_special_letters(w2)

        if stripped_equal and min(len(w1), len(w2)) >= 3:
            return True

        return self._is_distance_one(w1, w2)

    def _get_word_similarity_matches(self, a: str, b: str) -> dict:
        aw = self._cmp_words(a)
        bw = self._cmp_words(b)
        matched_a: set[int] = set()
        matched_b: set[int] = set()
        matches = 0
        non_dj_matches = 0

        for i, w1 in enumerate(aw):
            for j, w2 in enumerate(bw):
                if i in matched_a or j in matched_b:
                    continue
                if self._are_similar_words(w1, w2):
                    matched_a.add(i)
                    matched_b.add(j)
                    matches += 1
                    if not (self._is_generic_dj_word(w1) and self._is_generic_dj_word(w2)):
                        non_dj_matches += 1
                    break

        return {
            "aw": aw,
            "bw": bw,
            "matched_a": matched_a,
            "matched_b": matched_b,
            "matches": matches,
            "non_dj_matches": non_dj_matches,
        }

    def _similarity_reason(self, a: str, b: str) -> str | None:
        a0 = self._cmp_key(a)
        b0 = self._cmp_key(b)
        if not a0 or not b0:
            return None
        if a0 == b0:
            return "exact_key"

        aw = self._cmp_words(a)
        bw = self._cmp_words(b)
        if aw and bw:
            matched_a: set[int] = set()
            matched_b: set[int] = set()
            matches = 0
            non_dj_matches = 0

            for i, w1 in enumerate(aw):
                if i in matched_a:
                    continue
                for j, w2 in enumerate(bw):
                    if j in matched_b:
                        continue
                    if self._are_similar_words(w1, w2):
                        matched_a.add(i)
                        matched_b.add(j)
                        matches += 1
                        if not (self._is_generic_dj_word(w1) and self._is_generic_dj_word(w2)):
                            non_dj_matches += 1
                        break
                if non_dj_matches >= 2:
                    return "word2"

            if self._word_count_for_anagram_rule(a) >= 2 and self._word_count_for_anagram_rule(b) >= 2:
                for i, w1 in enumerate(aw):
                    if i in matched_a:
                        continue
                    for j, w2 in enumerate(bw):
                        if j in matched_b:
                            continue
                        if self._signature_letters(w1) == self._signature_letters(w2):
                            matched_a.add(i)
                            matched_b.add(j)
                            matches += 1
                            if not (self._is_generic_dj_word(w1) and self._is_generic_dj_word(w2)):
                                non_dj_matches += 1
                            break
                    if non_dj_matches >= 2:
                        return "word2"

        if self._strip_special_letters(a0) == self._strip_special_letters(b0):
            return "special_letters"
        aw = self._cmp_words(a)
        bw = self._cmp_words(b)

        if not any(len(w) <= 2 for w in aw + bw) and self._is_distance_one(a0, b0):
            return "distance_one"
        if self._word_count_for_anagram_rule(a) >= 2 and self._word_count_for_anagram_rule(b) >= 2:
            if self._signature_letters(a0) == self._signature_letters(b0):
                return "anagram"
        return None

    def _are_similar_artists(self, a: str, b: str) -> bool:
        return self._similarity_reason(a, b) is not None

    def _artist_has_unmatched_words_in_word2(self, candidate: str, other: str) -> bool:
        if self._similarity_reason(candidate, other) != "word2":
            return False
        details = self._get_word_similarity_matches(candidate, other)
        if details["matches"] < 2:
            return False
        return len(details["matched_a"]) < len(details["aw"])

    def _should_offer_split_for_word2(self, a: str, b: str) -> bool:
        return self._artist_has_unmatched_words_in_word2(a, b) or self._artist_has_unmatched_words_in_word2(b, a)

    def _get_split_candidates_for_cluster(self, cluster: list[str]) -> dict[str, bool]:
        return {
            name: any(self._artist_has_unmatched_words_in_word2(name, other) for other in cluster if other != name)
            for name in cluster
        }

    def _tokenize_split_text(self, text: str) -> list[str]:
        s = self._normalize_artist(text)
        for ch in ["־", "–", "—"]:
            s = s.replace(ch, "-")
        s = s.replace("-", " - ")
        return [part for part in s.split() if part]

    def _artist_word_count(self, artist_name: str) -> int:
        return len([t for t in self._tokenize_split_text(artist_name) if t != "-"])

    def _find_artist_span_in_candidate(self, candidate: str, artist_name: str) -> tuple[int, int] | None:
        candidate_tokens = self._tokenize_split_text(candidate)
        artist_tokens = [t for t in self._tokenize_split_text(artist_name) if t != "-"]
        if not candidate_tokens or not artist_tokens:
            return None

        for start in range(len(candidate_tokens)):
            ci = start
            first_idx: int | None = None
            last_idx: int | None = None
            ok = True

            for artist_word in artist_tokens:
                while ci < len(candidate_tokens) and candidate_tokens[ci] == "-":
                    ci += 1
                if ci >= len(candidate_tokens):
                    ok = False
                    break

                matches = self._are_similar_words(self._cmp_key(candidate_tokens[ci]), self._cmp_key(artist_word))
                if not matches:
                    curr_word = candidate_tokens[ci]
                    if len(curr_word) > 1 and curr_word.startswith("ו"):
                        without_vav = curr_word[1:]
                        if self._are_similar_words(self._cmp_key(without_vav), self._cmp_key(artist_word)):
                            matches = True

                if not matches:
                    ok = False
                    break

                if first_idx is None:
                    first_idx = ci
                last_idx = ci
                ci += 1

                while ci < len(candidate_tokens) and candidate_tokens[ci] == "-":
                    ci += 1

            if ok and first_idx is not None and last_idx is not None:
                return (first_idx, last_idx)

        return None

    def _get_unified_split_suggestion(self, candidate: str, artists_pool: list[str]) -> tuple[str, str] | None:
        candidate = self._normalize_artist(candidate)
        if not candidate:
            return None

        candidate_tokens = [t for t in self._tokenize_split_text(candidate) if t != "-"]
        if not candidate_tokens:
            return None

        options: list[tuple[tuple[int, int, int], tuple[str, str]]] = []

        for artist in artists_pool:
            artist = self._normalize_artist(artist)
            if not artist or artist == candidate:
                continue

            artist_tokens = [t for t in self._tokenize_split_text(artist) if t != "-"]
            if not artist_tokens:
                continue

            used_candidate_indices: set[int] = set()
            matched_all = True
            exact_matches = 0

            for aw in artist_tokens:
                found_idx = -1
                found_exact = False

                for idx, cw in enumerate(candidate_tokens):
                    if idx in used_candidate_indices:
                        continue

                    cw_key = self._cmp_key(cw)
                    aw_key = self._cmp_key(aw)

                    match = self._are_similar_words(cw_key, aw_key)
                    exact = (cw_key == aw_key)

                    if not match and cw.startswith("ו") and len(cw) > 1:
                        stripped = cw[1:]
                        stripped_key = self._cmp_key(stripped)
                        match = self._are_similar_words(stripped_key, aw_key)
                        exact = (stripped_key == aw_key)

                    if match:
                        found_idx = idx
                        found_exact = exact
                        break

                if found_idx == -1:
                    matched_all = False
                    break

                used_candidate_indices.add(found_idx)
                if found_exact:
                    exact_matches += 1

            if not matched_all:
                continue

            remaining_tokens = [cw for idx, cw in enumerate(candidate_tokens) if idx not in used_candidate_indices]
            if not remaining_tokens:
                continue

            if remaining_tokens and remaining_tokens[0].startswith("ו") and len(remaining_tokens[0]) > 1:
                remaining_tokens[0] = remaining_tokens[0][1:]

            secondary_part = self._normalize_artist(" ".join(remaining_tokens))
            if not secondary_part:
                continue

            sec_key = self._cmp_key(secondary_part)
            artist_key = self._cmp_key(artist)

            if sec_key and artist_key:
                if artist_key in sec_key or sec_key in artist_key:
                    continue
                if self._similarity_reason(secondary_part, artist) is not None:
                    continue

            real_secondary_name = secondary_part
            for known_artist in artists_pool:
                norm_known = self._normalize_artist(known_artist)
                if not norm_known or norm_known == candidate or norm_known == artist:
                    continue
                if self._similarity_reason(secondary_part, norm_known) is not None:
                    real_secondary_name = norm_known
                    break

            score = (
                -len(artist_tokens),
                exact_matches,
                -len(self._cmp_key(artist))
            )
            options.append((score, (real_secondary_name, artist)))

        if not options:
            return None

        options.sort(key=lambda x: x[0], reverse=True)
        return options[0][1]

    def _get_candidate_split_suggestion(self, candidate: str, cluster: list[str]) -> tuple[str, str] | None:
        return self._get_unified_split_suggestion(candidate, self._get_all_artist_names())

    def _get_split_suggestions_for_cluster(self, cluster: list[str]) -> dict[str, tuple[str, str] | None]:
        all_artists = self._get_all_artist_names()
        return {
            name: self._get_unified_split_suggestion(name, all_artists)
            for name in cluster
        }

    def _get_two_artist_split_suggestion(self, a: str, b: str) -> tuple[str, str] | None:
        pool_a = self._get_all_artist_names()
        if b not in pool_a:
            pool_a = pool_a + [b]

        sug_a = self._get_unified_split_suggestion(a, pool_a)
        if sug_a:
            return sug_a

        pool_b = self._get_all_artist_names()
        if a not in pool_b:
            pool_b = pool_b + [a]

        sug_b = self._get_unified_split_suggestion(b, pool_b)
        if sug_b:
            return sug_b

        return (a, b)

    def _load_similar_ignore_pairs(self):
        self._similar_ignore_pairs = set()
        if not os.path.exists(self._similar_ignore_file_path):
            return
        try:
            with open(self._similar_ignore_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item):
                        self._similar_ignore_pairs.add(self._pair_key(item[0], item[1]))
        except Exception:
            self._similar_ignore_pairs = set()

    def _save_similar_ignore_pairs(self):
        try:
            with open(self._similar_ignore_file_path, "w", encoding="utf-8") as f:
                json.dump([[a, b] for (a, b) in sorted(self._similar_ignore_pairs)], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _save_ignored_pairs_for_cluster(self, cluster_entries: list[dict[str, str]], ignored_displays: list[str]):
        ignored_set = set(ignored_displays or [])
        if len(ignored_set) < 2:
            return

        ignored_entries = [entry for entry in cluster_entries if entry.get("display") in ignored_set]
        for i in range(len(ignored_entries)):
            for j in range(i + 1, len(ignored_entries)):
                a = ignored_entries[i]["name"]
                b = ignored_entries[j]["name"]
                self._similar_ignore_pairs.add(self._pair_key(a, b))

        self._save_similar_ignore_pairs()

    def _load_english_hidden_aliases_map(self):
        self._english_hidden_aliases_map = {}
        if not os.path.exists(self._english_hidden_aliases_file_path):
            return

        try:
            with open(self._english_hidden_aliases_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            out: dict[str, list[str]] = {}
            if isinstance(data, dict):
                for artist, aliases in data.items():
                    if not isinstance(artist, str) or not isinstance(aliases, list):
                        continue

                    norm_artist = self._normalize_artist(artist)
                    if not norm_artist:
                        continue

                    normalized_aliases = []
                    for alias in aliases:
                        if not isinstance(alias, str):
                            continue
                        norm_alias = self._normalize_artist(alias)
                        if norm_alias and norm_alias != norm_artist:
                            normalized_aliases.append(norm_alias)

                    out[norm_artist] = sorted(set(normalized_aliases))

            self._english_hidden_aliases_map = out

        except Exception:
            self._english_hidden_aliases_map = {} 

    def _save_english_hidden_aliases_map(self):
        try:
            with open(self._english_hidden_aliases_file_path, "w", encoding="utf-8") as f:
                json.dump(self._english_hidden_aliases_map, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        
    def _load_aliases_from_file(self):
        if not os.path.exists(self._aliases_file_path):
            self._aliases_map = {}
            return
        try:
            with open(self._aliases_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            out: dict[str, list[str]] = {}
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, list):
                        nk = self._normalize_artist(k)
                        out[nk] = [self._normalize_artist(x) for x in v if isinstance(x, str) and self._normalize_artist(x)]
            self._aliases_map = out
        except Exception:
            self._aliases_map = {}

    def _save_aliases_to_file(self):
        try:
            with open(self._aliases_file_path, "w", encoding="utf-8") as f:
                json.dump(self._aliases_map, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_artists_from_file(self, progress_callback=None):
        if not os.path.exists(self._artists_file_path):
            if progress_callback:
                progress_callback(1, 1)
            return 0

        try:
            with open(self._artists_file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total = max(1, len(lines))
            loaded = 0

            for idx, line in enumerate(lines, start=1):
                name = self._normalize_artist(line)
                if name:
                    self._add_artist_to_list(name, persist=False, refresh_ui=False)
                    loaded += 1

                if progress_callback:
                    progress_callback(idx, total)

            self._refresh_artists_list_widget()
            return loaded

        except Exception:
            if progress_callback:
                progress_callback(1, 1)
            return 0

    def save_artists_to_file(self):
        try:
            with open(self._artists_file_path, "w", encoding="utf-8") as f:
                for a in sorted(self._artists_set):
                    f.write(a + "\n")
        except Exception:
            pass

    def _is_english_artist(self, name: str) -> bool:
        name = self._normalize_artist(name)
        has_english = any(("A" <= ch <= "Z") or ("a" <= ch <= "z") for ch in name)
        has_hebrew = any("א" <= ch <= "ת" for ch in name)
        return has_english and not has_hebrew

    def _load_english_hidden_artists(self):
        self._english_hidden_artists = set()
        if not os.path.exists(self._english_hidden_file_path):
            return
        try:
            with open(self._english_hidden_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    name = self._normalize_artist(line)
                    if name:
                        self._english_hidden_artists.add(name)
        except Exception:
            self._english_hidden_artists = set()

    def _save_english_hidden_artists(self):
        try:
            with open(self._english_hidden_file_path, "w", encoding="utf-8") as f:
                for a in sorted(self._english_hidden_artists):
                    f.write(a + "\n")
        except Exception:
            pass

    def _load_english_visibility_state(self):
        self._english_artists_visible = True
        if not os.path.exists(self._english_visible_file_path):
            return
        try:
            with open(self._english_visible_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._english_artists_visible = bool(data.get("visible", True))
        except Exception:
            self._english_artists_visible = True

    def _save_english_visibility_state(self):
        try:
            with open(self._english_visible_file_path, "w", encoding="utf-8") as f:
                json.dump({"visible": self._english_artists_visible}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _update_english_toggle_button_text(self):
        if self._english_artists_visible:
            self.toggle_english_btn.setText("הסתרת אמנים באנגלית")
            self.toggle_english_btn.setStyleSheet("""
                QPushButton {
                    background: #fff4d6;
                    color: #6a4b00;
                    border: 1px solid #e3c97a;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size:15px;
                    font-weight:800;
                }
                QPushButton:hover {
                    background: #ffe8a3;
                }
            """)
        else:
            self.toggle_english_btn.setText("הצגת אמנים באנגלית")
            self.toggle_english_btn.setStyleSheet("""
                QPushButton {
                    background: #dff6e4;
                    color: #1f5c2f;
                    border: 1px solid #9ed0a8;
                    border-radius: 8px;
                    padding: 8px 16px;
                    font-size:15px;
                    font-weight:800;
                }
                QPushButton:hover {
                    background: #ccefd5;
                }
            """)

    def _apply_hidden_english_mode_on_startup(self):
        to_hide = [name for name in list(self._artists_set) if self._is_english_artist(name)]
        for name in to_hide:
            self._hide_english_artist_with_aliases(name)

        self._save_english_hidden_artists()
        self._save_english_hidden_aliases_map()
        self._save_aliases_to_file()
        self.save_artists_to_file()

    def toggle_english_artists_visibility(self):
        if self._english_artists_visible:
            to_hide = [name for name in list(self._artists_set) if self._is_english_artist(name)]
            for name in to_hide:
                self._hide_english_artist_with_aliases(name)
            self._english_artists_visible = False
        else:
            names_to_restore = sorted(self._english_hidden_artists)
            for name in names_to_restore:
                self._restore_hidden_english_artist_with_aliases(name)
            self._english_artists_visible = True

        self._save_english_hidden_artists()
        self._save_english_hidden_aliases_map()
        self._save_aliases_to_file()
        self._save_english_visibility_state()
        self.save_artists_to_file()
        self._refresh_artists_list_widget()
        self._update_english_toggle_button_text()

    def resolve_artist_for_song_name(self, song_name: str) -> str | None:
        s = self._normalize_artist(song_name)
        if not s:
            return None
        if s in self._artists_set:
            return s
        for artist, aliases in self._aliases_map.items():
            if s in aliases:
                return artist
        return None

    def _get_all_artist_names(self) -> list[str]:
        return sorted(self._artists_set)

    def _get_compare_entries(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []

        for artist in sorted(self._artists_set):
            entries.append({
                "name": artist,
                "kind": "artist",
                "owner": artist,
                "display": artist,
            })

        for owner, aliases in self._aliases_map.items():
            owner = self._normalize_artist(owner)
            if owner not in self._artists_set:
                continue

            for alias in sorted(set(aliases)):
                alias = self._normalize_artist(alias)
                if not alias:
                    continue
                entries.append({
                    "name": alias,
                    "kind": "alias",
                    "owner": owner,
                    "display": f'{alias} (שם זה הוא כינוי לאמן "{owner}")',
                })

        return entries

    def _compare_entry_id(self, entry: dict[str, str]) -> tuple[str, str, str]:
        return (
            entry.get("kind", ""),
            self._normalize_artist(entry.get("owner", "")),
            self._normalize_artist(entry.get("name", "")),
        )

    def _compare_entries_same(self, a: dict[str, str], b: dict[str, str]) -> bool:
        return self._compare_entry_id(a) == self._compare_entry_id(b)

    def _compare_entries_same_owner(self, a: dict[str, str], b: dict[str, str]) -> bool:
        return self._normalize_artist(a.get("owner", "")) == self._normalize_artist(b.get("owner", ""))

    def _compare_entries_belong_to_same_artist(self, a: dict[str, str], b: dict[str, str]) -> bool:
        owner_a = self._compare_entry_to_target_artist(a)
        owner_b = self._compare_entry_to_target_artist(b)

        if owner_a and owner_b:
            return owner_a == owner_b

        return self._compare_entries_same_owner(a, b)

    def _is_compare_stage_match(self, a: dict[str, str], b: dict[str, str], stage: int) -> bool:
        if self._compare_entries_belong_to_same_artist(a, b):
            return False

        ak = a.get("kind")
        bk = b.get("kind")

        if stage == self.COMPARE_STAGE_ARTISTS_ONLY:
            return ak == "artist" and bk == "artist"
        if stage == self.COMPARE_STAGE_ARTISTS_TO_ALIASES_ONLY:
            return (ak == "artist" and bk == "alias") or (ak == "alias" and bk == "artist")
        if stage == self.COMPARE_STAGE_ALIASES_ONLY:
            return ak == "alias" and bk == "alias"
        return False

    def _find_similar_pairs_for_stage(self, stage: int) -> list[tuple[dict[str, str], dict[str, str]]]:
        entries = self._get_compare_entries()
        pairs: list[tuple[dict[str, str], dict[str, str]]] = []

        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a = entries[i]
                b = entries[j]

                if self._compare_entries_belong_to_same_artist(a, b):
                    continue
                if not self._is_compare_stage_match(a, b, stage):
                    continue
                if self._pair_key(a["name"], b["name"]) in self._similar_ignore_pairs:
                    continue
                if self._are_similar_artists(a["name"], b["name"]):
                    pairs.append((a, b))

        return pairs

    def _build_cluster_from_entries(
        self,
        seed_a: dict[str, str],
        seed_b: dict[str, str],
        stage: int,
    ) -> list[dict[str, str]]:
        entries = self._get_compare_entries()
        cluster: list[dict[str, str]] = [seed_a, seed_b]

        changed = True
        while changed:
            changed = False
            for entry in entries:
                if any(self._compare_entries_same(entry, existing) for existing in cluster):
                    continue

                for existing in cluster:
                    if self._compare_entries_belong_to_same_artist(entry, existing):
                        continue
                    if not self._is_compare_stage_match(entry, existing, stage):
                        continue
                    if self._pair_key(entry["name"], existing["name"]) in self._similar_ignore_pairs:
                        continue
                    if self._are_similar_artists(entry["name"], existing["name"]):
                        cluster.append(entry)
                        changed = True
                        break

        unique_cluster: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()

        for entry in cluster:
            eid = self._compare_entry_id(entry)
            if eid in seen:
                continue
            seen.add(eid)
            unique_cluster.append(entry)

        unique_cluster.sort(key=lambda x: (x.get("kind", ""), x.get("owner", ""), x.get("name", "")))
        return unique_cluster

    def _find_next_compare_cluster(self) -> tuple[int, list[dict[str, str]]] | None:
        for stage in (
            self.COMPARE_STAGE_ARTISTS_ONLY,
            self.COMPARE_STAGE_ARTISTS_TO_ALIASES_ONLY,
            self.COMPARE_STAGE_ALIASES_ONLY,
        ):
            pairs = self._find_similar_pairs_for_stage(stage)
            if not pairs:
                continue

            seed_a, seed_b = pairs[0]
            cluster = self._build_cluster_from_entries(seed_a, seed_b, stage)
            if len(cluster) >= 2:
                return stage, cluster

        return None

    def _compare_entry_to_target_artist(self, entry: dict[str, str]) -> str | None:
        if entry.get("kind") == "artist":
            name = self._normalize_artist(entry.get("name", ""))
            return name if name in self._artists_set else None

        owner = self._normalize_artist(entry.get("owner", ""))
        return owner if owner in self._artists_set else None

    def _artist_matches_search(self, artist_name: str, query: str) -> bool:
        query = self._normalize_artist(query)
        if not query:
            return True

        artist_name = self._normalize_artist(artist_name)
        if query.casefold() in artist_name.casefold():
            return True

        return self._cmp_key(query).casefold() in self._cmp_key(artist_name).casefold()

    def filter_artists_list(self, *_args):
        query = self.search_edit.text().strip() if hasattr(self, "search_edit") else ""
        for row in range(self.artists_list.count()):
            item = self.artists_list.item(row)
            widget = self.artists_list.itemWidget(item)
            if isinstance(widget, ArtistRowWidget):
                item.setHidden(not self._artist_matches_search(widget.artist_name, query))

    def _build_similar_cluster(self, seed: str) -> list[str]:
        seed = self._normalize_artist(seed)
        names = self._get_all_comparable_names()
        if seed not in names:
            return []

        cluster = {seed}
        changed = True
        while changed:
            changed = False
            for n in names:
                if n in cluster:
                    continue
                for c in list(cluster):
                    if self._pair_key(n, c) in self._similar_ignore_pairs:
                        continue
                    if self._are_from_same_owner(n, c):
                        continue
                    if self._are_similar_artists(n, c):
                        cluster.add(n)
                        changed = True
                        break
        return sorted(cluster)

    def _find_next_cluster(self) -> list[str] | None:
        for seed in self._get_all_comparable_names():
            cluster = self._build_similar_cluster(seed)
            if len(cluster) < 2:
                continue
            for i in range(len(cluster)):
                for j in range(i + 1, len(cluster)):
                    if self._pair_key(cluster[i], cluster[j]) in self._similar_ignore_pairs:
                        continue
                    if self._are_from_same_owner(cluster[i], cluster[j]):
                        continue
                    return cluster
        return None

    def _add_artist_to_list(self, name: str, persist: bool, refresh_ui: bool = True) -> bool:
        name = self._normalize_artist(name)
        if not name:
            return False

        if name in self._artists_set:
            return False

        if name in self._english_hidden_artists:
            return False

        self._artists_set.add(name)

        if refresh_ui:
            self._refresh_artists_list_widget()

        if persist:
            self.save_artists_to_file()
        return True

    def _refresh_artists_list_widget(self):
        self.artists_list.clear()

        for name in sorted(self._artists_set):
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 38))

            row_widget = ArtistRowWidget(name)
            row_widget.deleteRequested.connect(self.delete_artist_by_name)
            row_widget.editRequested.connect(self.edit_artist_by_name)
            row_widget.aliasesRequested.connect(self.open_aliases_for_artist)

            self.artists_list.addItem(item)
            self.artists_list.setItemWidget(item, row_widget)

        self.filter_artists_list()

    def add_single_artist(self):
        raw_name = self.single_edit.text()
        name, error_code, alias_owner = self._validate_artist_for_external_add(raw_name)

        if error_code:
            display_name = name or self._normalize_artist(raw_name) or "ללא שם"
            QMessageBox.warning(self, "שגיאה", self._artist_add_error_message(display_name, error_code, alias_owner))
            return

        if self._add_artist_to_list(name, persist=True):
            self.single_edit.clear()

    def add_multiple_artists(self):
        text = self.multi_edit.toPlainText()
        if not text.strip():
            return

        changed_any = False
        candidates: list[str] = []
        skipped_messages: list[str] = []
        seen_messages: set[str] = set()

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            candidates.extend([p.strip() for p in line.replace(";", ",").split(",") if p.strip()])

        for c in candidates:
            name, error_code, alias_owner = self._validate_artist_for_external_add(c)
            if error_code:
                display_name = name or self._normalize_artist(c) or "ללא שם"
                msg = self._artist_add_error_message(display_name, error_code, alias_owner)
                if msg not in seen_messages:
                    skipped_messages.append(msg)
                    seen_messages.add(msg)
                continue
            changed_any = self._add_artist_to_list(name, persist=False) or changed_any

        if changed_any:
            self.save_artists_to_file()

        self.multi_edit.clear()

        if skipped_messages:
            extra = ""
            if len(skipped_messages) > 12:
                extra = f"\n... ועוד {len(skipped_messages) - 12} הודעות."
            QMessageBox.warning(self, "חלק מהאמנים לא נוספו", "\n".join(skipped_messages[:12]) + extra)

    def _read_artist_from_file(self, file_path: str) -> str | None:
        try:
            audio = MutagenFile(file_path, easy=True)
            if not audio:
                return None
            v = audio.get("artist")
            if v:
                return ", ".join(str(x) for x in v if x) if isinstance(v, list) else str(v)
            v = audio.get("albumartist")
            if v:
                return ", ".join(str(x) for x in v if x) if isinstance(v, list) else str(v)
            return None
        except Exception:
            return None

    def _split_artists(self, raw: str) -> list[str]:
        s = (raw or "").strip()
        if not s:
            return []
        for sep in [";", "/", "\\", "|"]:
            s = s.replace(sep, ",")
        return [p.strip() for p in s.split(",") if p.strip()]

    def import_artists_from_folder(self):
        if MutagenFile is None:
            QMessageBox.warning(self, "חסרה ספרייה", "כדי לייבא מטא-דאטה משירים צריך להתקין mutagen:\n\npip install mutagen")
            return

        main_window = self.window()
        folder = getattr(getattr(main_window, "folder_selector", None), "current_folder", "") or ""
        folder = folder.strip()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, "נתיב לא תקין", "בחר/י קודם תיקייה חוקית בשדה 'בחר תיקיית שירים'.")
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("ייבוא אמנים")
        msg.setText(f"האם להתחיל סריקה של מטא-דאטה בתיקייה?\n\n{folder}\n\nכולל כל תתי התיקיות.")
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton("כן", QMessageBox.ButtonRole.YesRole)
        no_btn = msg.addButton("לא", QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(no_btn)
        msg.exec()
        if msg.clickedButton() is not yes_btn:
            return

        supported_ext = {".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".opus", ".wav", ".aiff", ".aif"}
        found_artists: set[str] = set()
        files_scanned = 0
        invalid_names = 0
        skipped_existing = 0
        skipped_aliases = 0

        for path in Path(folder).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in supported_ext:
                continue
            files_scanned += 1
            artist = self._read_artist_from_file(str(path))
            if artist:
                for a in self._split_artists(artist):
                    cleaned_name = self._sanitize_artist_name(a)
                    if cleaned_name:
                        found_artists.add(cleaned_name)
                    elif self._normalize_artist(a):
                        invalid_names += 1

        if not found_artists:
            QMessageBox.information(self, "ייבוא אמנים", f"נסרקו {files_scanned} קבצים תומכים, ולא נמצאו שמות אמנים תקינים לייבוא.")
            return

        added = 0
        for a in sorted(found_artists):
            if a in self._artists_set:
                skipped_existing += 1
                continue
            if self._find_alias_owner(a):
                skipped_aliases += 1
                continue
            if self._add_artist_to_list(a, persist=False):
                added += 1

        if added:
            self.save_artists_to_file()

        summary_lines = [
            f"נסרקו {files_scanned} קבצים.",
            f"נמצאו {len(found_artists)} שמות אמנים תקינים.",
            f"נוספו {added} אמנים חדשים לרשימה.",
        ]
        if skipped_existing:
            summary_lines.append(f"{skipped_existing} שמות כבר היו קיימים ברשימה ולא נוספו שוב.")
        if skipped_aliases:
            summary_lines.append(f"{skipped_aliases} שמות כבר קיימים ככינויים ולא נוספו.")
        if invalid_names:
            summary_lines.append(f"{invalid_names} שמות נפסלו כי לא הכילו אותיות בעברית/אנגלית.")

        QMessageBox.information(self, "ייבוא אמנים", "\n".join(summary_lines))

    def delete_checked_artists(self):
        checked_artists: list[str] = []
        for row in range(self.artists_list.count()):
            item = self.artists_list.item(row)
            widget = self.artists_list.itemWidget(item)
            if isinstance(widget, ArtistRowWidget) and widget.checkbox.isChecked():
                checked_artists.append(widget.artist_name)

        if not checked_artists:
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("אישור מחיקה")
        msg.setText(f'האם אתה בטוח שאתה רוצה למחוק {len(checked_artists)} אמנים?')
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton("כן", QMessageBox.ButtonRole.YesRole)
        no_btn = msg.addButton("לא", QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(no_btn)
        msg.exec()
        if msg.clickedButton() is not yes_btn:
            return

        for artist_name in checked_artists:
            self._delete_artist_by_name_internal(artist_name)

        self.save_artists_to_file()
        self._save_aliases_to_file()
        self._save_english_hidden_artists()
        self._save_english_hidden_aliases_map()

    def check_all_artists(self):
        for row in range(self.artists_list.count()):
            widget = self.artists_list.itemWidget(self.artists_list.item(row))
            if isinstance(widget, ArtistRowWidget):
                widget.checkbox.setChecked(True)

    def uncheck_all_artists(self):
        for row in range(self.artists_list.count()):
            widget = self.artists_list.itemWidget(self.artists_list.item(row))
            if isinstance(widget, ArtistRowWidget):
                widget.checkbox.setChecked(False)

    def _delete_artist_by_name_internal(self, artist_name: str):
        artist_name = self._normalize_artist(artist_name)
        if not artist_name:
            return

        self._artists_set.discard(artist_name)
        self._aliases_map.pop(artist_name, None)

        self._english_hidden_artists.discard(artist_name)
        self._english_hidden_aliases_map.pop(artist_name, None)

        self._refresh_artists_list_widget()

    def delete_artist_by_name(self, artist_name: str):
        if artist_name not in self._artists_set:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("אישור מחיקה")
        msg.setText(f'האם אתה בטוח שאתה רוצה למחוק את האמן "{artist_name}"?')
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton("כן", QMessageBox.ButtonRole.YesRole)
        no_btn = msg.addButton("לא", QMessageBox.ButtonRole.NoRole)
        msg.setDefaultButton(no_btn)
        msg.exec()
        if msg.clickedButton() is not yes_btn:
            return
        self._delete_artist_by_name_internal(artist_name)
        self.save_artists_to_file()
        self._save_aliases_to_file()
        self._save_english_hidden_artists()
        self._save_english_hidden_aliases_map()

    def edit_artist_by_name(self, old_name: str):
        if old_name not in self._artists_set:
            return

        new_name, ok = QInputDialog.getText(self, "עריכת אמן", "שם אמן חדש:", text=old_name)
        if not ok:
            return

        sanitized_name = self._sanitize_artist_name(new_name)
        if not sanitized_name:
            QMessageBox.warning(self, "שגיאה", "שם האמן חייב להכיל אותיות בעברית או באנגלית בלבד.")
            return

        new_name = sanitized_name
        if new_name == old_name:
            return

        if new_name in self._artists_set:
            QMessageBox.warning(self, "שגיאה", f'האמן "{new_name}" כבר קיים ברשימה.')
            return

        alias_owner = self._find_alias_owner(new_name)
        if alias_owner and alias_owner != old_name:
            QMessageBox.warning(self, "שגיאה", f'השם "{new_name}" כבר קיים ככינוי לאמן "{alias_owner}".')
            return

        self._artists_set.discard(old_name)
        self._artists_set.add(new_name)

        aliases = self._aliases_map.pop(old_name, [])
        if aliases:
            self._aliases_map[new_name] = aliases

        for owner, owner_aliases in list(self._aliases_map.items()):
            updated_aliases = []
            changed = False
            for alias in owner_aliases:
                if self._normalize_artist(alias) == old_name:
                    updated_aliases.append(new_name)
                    changed = True
                else:
                    updated_aliases.append(alias)

            if changed:
                normalized_aliases = sorted(set(self._normalize_artist(a) for a in updated_aliases if self._normalize_artist(a)))
                self._aliases_map[owner] = normalized_aliases

        self._save_aliases_to_file()
        self._refresh_artists_list_widget()
        self.save_artists_to_file()

    def open_aliases_for_artist(self, artist_name: str):
        dlg = AliasesDialog(self, artist_name, self._aliases_map.get(artist_name, []))
        if dlg.exec():
            self._aliases_map[artist_name] = sorted(set(dlg.get_aliases()))
            self._save_aliases_to_file()

    def compare_similar_artists(self):
        try:
            while True:
                found = self._find_next_compare_cluster()
                if not found:
                    QMessageBox.information(
                        self,
                        "השוואת אמנים דומים",
                        "לא נמצאו שמות אמנים דומים לפי הכללים שהוגדרו."
                    )
                    return

                stage, cluster_entries = found

                if len(cluster_entries) == 2:
                    entry_a, entry_b = cluster_entries[0], cluster_entries[1]
                    a_name = entry_a["name"]
                    b_name = entry_b["name"]

                    offer_split = (
                        entry_a.get("kind") == "artist"
                        and entry_b.get("kind") == "artist"
                        and self._should_offer_split_for_word2(a_name, b_name)
                    )
                    split_initial_values = self._get_two_artist_split_suggestion(a_name, b_name) if offer_split else None

                    comparison_mode = "regular"
                    primary_artist_name = ""
                    alias_owner_name = ""

                    if entry_a.get("kind") == "artist" and entry_b.get("kind") == "alias":
                        comparison_mode = "artist_vs_alias"
                        primary_artist_name = entry_a["name"]
                        alias_owner_name = entry_b.get("owner", "")
                    elif entry_b.get("kind") == "artist" and entry_a.get("kind") == "alias":
                        comparison_mode = "artist_vs_alias"
                        primary_artist_name = entry_b["name"]
                        alias_owner_name = entry_a.get("owner", "")

                    dlg = TwoArtistsDialog(
                        self,
                        entry_a["display"],
                        entry_b["display"],
                        self._similarity_reason(a_name, b_name),
                        offer_split,
                        split_initial_values,
                        comparison_mode=comparison_mode,
                        primary_artist_name=primary_artist_name,
                        alias_owner_name=alias_owner_name,
                    )
                    if dlg.exec() != QDialog.DialogCode.Accepted:
                        return

                    res = dlg.get_result()

                    if res.get("ignore_pair"):
                        self._similar_ignore_pairs.add(self._pair_key(a_name, b_name))
                        self._save_similar_ignore_pairs()
                        continue

                    if offer_split and res.get("split_two_artists"):
                        name1 = self._normalize_artist(res.get("split_name_a") or "")
                        name2 = self._normalize_artist(res.get("split_name_b") or "")
                        if not name1 or not name2 or name1 == name2:
                            QMessageBox.warning(self, "שגיאה", "בפיצול חייבים למלא שני שמות אמנים שונים.")
                            continue

                        self._remove_name_entity(a_name)
                        self._remove_name_entity(b_name)
                        self._add_artist_to_list(name1, persist=False)
                        self._add_artist_to_list(name2, persist=False)

                        self._similar_ignore_pairs.add(self._pair_key(a_name, b_name))
                        self._save_similar_ignore_pairs()
                        self._save_aliases_to_file()
                        self.save_artists_to_file()
                        continue

                    fix_name = self._normalize_artist(res.get("fix_name") or "")
                    if fix_name:
                        self._add_artist_to_list(fix_name, persist=False)
                        self._absorb_name_into_artist(fix_name, a_name)
                        self._absorb_name_into_artist(fix_name, b_name)
                        self._save_aliases_to_file()
                        self.save_artists_to_file()
                        continue

                    if comparison_mode == "artist_vs_alias":
                        if dlg.rb_a.isChecked():
                            chosen_entry = entry_a if entry_a.get("kind") == "alias" else entry_b
                        else:
                            chosen_entry = entry_a if entry_a.get("kind") == "artist" else entry_b
                    else:
                        chosen_entry = entry_a if dlg.rb_a.isChecked() else entry_b

                    other_entry = entry_b if chosen_entry is entry_a else entry_a
                    chosen_kind = chosen_entry.get("kind")
                    other_kind = other_entry.get("kind")

                    if chosen_kind == "alias" and other_kind == "artist":
                        # User confirmed: other_entry (artist) is an alias of chosen_entry's owner.
                        # Remove the artist from main list and keep it only as an alias.
                        alias_owner = chosen_entry.get("owner", "")
                        if alias_owner and alias_owner in self._artists_set:
                            self._absorb_name_into_artist(alias_owner, other_entry["name"])
                        else:
                            self._remove_name_entity(other_entry["name"])
                        self._save_aliases_to_file()
                        self.save_artists_to_file()
                        continue

                    if chosen_kind == "artist" and other_kind == "alias":
                        self._remove_name_entity(other_entry["name"])
                        self._save_aliases_to_file()
                        self.save_artists_to_file()
                        continue

                    target_artist = self._compare_entry_to_target_artist(chosen_entry)
                    if target_artist in self._artists_set:
                        self._absorb_name_into_artist(target_artist, other_entry["name"])
                    else:
                        self._remove_name_entity(other_entry["name"])

                    self._save_aliases_to_file()
                    self.save_artists_to_file()
                    continue

                artists_for_dialog = [entry["display"] for entry in cluster_entries]

                split_candidates: dict[str, bool] = {}
                split_suggestions: dict[str, tuple[str, str] | None] = {}

                for entry in cluster_entries:
                    display_name = entry["display"]
                    if entry.get("kind") == "artist":
                        split_candidates[display_name] = any(
                            other.get("kind") == "artist"
                            and not self._compare_entries_same(entry, other)
                            and self._artist_has_unmatched_words_in_word2(entry["name"], other["name"])
                            for other in cluster_entries
                        )
                        split_suggestions[display_name] = self._get_unified_split_suggestion(
                            entry["name"],
                            self._get_all_artist_names()
                        )
                    else:
                        split_candidates[display_name] = False
                        split_suggestions[display_name] = None

                dlg = SimilarArtistsDialog(self, artists_for_dialog, split_candidates, split_suggestions)
                if dlg.exec() != QDialog.DialogCode.Accepted:
                    return

                selection = dlg.get_selection()
                main_artists_display: list[str] = selection.get("main_artists", [])
                # Backward compat: single main_artist fallback
                if not main_artists_display:
                    single = selection.get("main_artist")
                    if single:
                        main_artists_display = [single]
                ignored = selection.get("ignored", [])
                split_map = selection.get("split_map", {})

                entries_by_display = {entry["display"]: entry for entry in cluster_entries}

                normalized_split_map: dict[str, tuple[str, str]] = {}
                invalid_split = False

                for old_display, values in split_map.items():
                    entry = entries_by_display.get(old_display)
                    if not entry or entry.get("kind") != "artist":
                        invalid_split = True
                        break

                    name1 = self._normalize_artist(values[0] if len(values) > 0 else "")
                    name2 = self._normalize_artist(values[1] if len(values) > 1 else "")
                    if not name1 or not name2 or name1 == name2:
                        invalid_split = True
                        break

                    normalized_split_map[old_display] = (name1, name2)

                if invalid_split:
                    QMessageBox.warning(self, "שגיאה", "בכל פיצול חייבים להגדיר שני שמות שונים, ורק עבור אמן ראשי.")
                    continue

                auto_resolved_displays = set(ignored)
                auto_resolved_displays.update(normalized_split_map.keys())

                for entry in cluster_entries:
                    display_name = entry["display"]
                    if display_name in auto_resolved_displays:
                        continue

                    candidate_name = self._normalize_artist(entry["name"])
                    if not candidate_name:
                        continue

                    for split_name1, split_name2 in normalized_split_map.values():
                        matched_target = self._match_split_target_name(candidate_name, (split_name1, split_name2))
                        if matched_target:
                            auto_resolved_displays.add(display_name)
                            break

                unresolved_entries: list[dict[str, str]] = []
                for entry in cluster_entries:
                    if entry["display"] in auto_resolved_displays:
                        continue
                    unresolved_entries.append(entry)

                requires_main_artist = len(unresolved_entries) > 0

                if requires_main_artist and not main_artists_display:
                    QMessageBox.warning(
                        self,
                        "שגיאה",
                        'חייבים לבחור לפחות "אמן עיקרי" אחד, אלא אם כל השמות באשכול כבר נפתרו דרך פיצול או הוחרגו.'
                    )
                    continue

                active_names = [entry["display"] for entry in unresolved_entries]
                self._save_ignored_pairs_for_cluster(cluster_entries, ignored)

                for old_display, (name1, name2) in normalized_split_map.items():
                    entry = entries_by_display.get(old_display)
                    if not entry:
                        continue

                    old_name = self._normalize_artist(entry["name"])
                    self._remove_name_entity(old_name)

                    if name1 not in self._artists_set:
                        self._add_artist_to_list(name1, persist=False)
                    if name2 not in self._artists_set:
                        self._add_artist_to_list(name2, persist=False)

                for entry in cluster_entries:
                    display_name = entry["display"]
                    if display_name in ignored or display_name in normalized_split_map:
                        continue

                    candidate_name = self._normalize_artist(entry["name"])
                    if not candidate_name:
                        continue

                    for split_name1, split_name2 in normalized_split_map.values():
                        matched_target = self._match_split_target_name(candidate_name, (split_name1, split_name2))
                        if not matched_target:
                            continue

                        is_exact_match = self._cmp_key(candidate_name) == self._cmp_key(matched_target)
                        candidate_is_real_artist = candidate_name in self._artists_set
                        matched_target_is_same_artist = candidate_name == matched_target

                        if candidate_is_real_artist and matched_target_is_same_artist:
                            break

                        if is_exact_match:
                            self._remove_name_entity(candidate_name)
                        else:
                            self._absorb_name_into_artist(matched_target, candidate_name)
                        break

                main_entries_display_set = set(main_artists_display)
                if main_artists_display:
                    # Build a map: main_display -> (main_entry, target_artist)
                    main_targets: list[tuple[str, dict[str, str], str]] = []
                    for md in main_artists_display:
                        me = entries_by_display.get(md)
                        ta = self._compare_entry_to_target_artist(me) if me else None
                        if ta:
                            main_targets.append((md, me, ta))

                    if len(main_targets) == 1:
                        # Single main artist – absorb all unresolved under it
                        _, main_entry, target_artist = main_targets[0]
                        for display_name in active_names:
                            entry = entries_by_display.get(display_name)
                            if not entry or entry is main_entry:
                                continue
                            self._absorb_name_into_artist(target_artist, entry["name"])
                    elif len(main_targets) >= 2:
                        # Multiple main artists – each absorbs only similar artists
                        for display_name in active_names:
                            entry = entries_by_display.get(display_name)
                            if not entry or display_name in main_entries_display_set:
                                continue
                            entry_name = entry["name"]
                            # Find which main artist this entry is similar to
                            best_main = None
                            for md, me, ta in main_targets:
                                if self._are_similar_artists(entry_name, me["name"]):
                                    best_main = ta
                                    break
                            if best_main:
                                self._absorb_name_into_artist(best_main, entry_name)
                            else:
                                # Entry is in the cluster via transitivity but not directly
                                # similar to either main – absorb under the first main artist
                                self._absorb_name_into_artist(main_targets[0][2], entry_name)

                self._save_aliases_to_file()
                self.save_artists_to_file()

        except Exception:
            QMessageBox.critical(
                self,
                "שגיאה בהשוואת אמנים",
                "אירעה שגיאה בזמן השוואת שמות דומים.\n\n" + traceback.format_exc()
            )
