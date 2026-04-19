"""
Settings Manager — persists user-chosen defaults so they are restored on
the next application launch.

The settings file is a simple JSON document stored next to the other app-data
files.  It records the state of every user-visible option in every tab so that
clicking "שמור הגדרות" snapshots everything, and on the next startup the
application can silently apply them.
"""

from __future__ import annotations

import json
import os
from typing import Any

from shared import app_data_path

_SETTINGS_FILE = "user_settings.json"


class SettingsManager:
    """Read / write a flat key-value store backed by a JSON file."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._load()

    # ── public API ─────────────────────────────────────────────────────
    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def save(self) -> None:
        path = self._settings_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def has_saved_settings(self) -> bool:
        return os.path.isfile(self._settings_path()) and bool(self._data)

    def clear(self) -> None:
        self._data.clear()
        path = self._settings_path()
        if os.path.isfile(path):
            try:
                os.remove(path)
            except Exception:
                pass

    # ── internal ───────────────────────────────────────────────────────
    def _settings_path(self) -> str:
        return app_data_path(_SETTINGS_FILE)

    def _load(self) -> None:
        path = self._settings_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    # ── convenience: collect from a SortingTab ─────────────────────────
    def collect_sorting_tab(self, tab) -> None:
        """Read every user option from *tab* and store it."""
        self.set("sorting.sort_type", tab.step_sort_type.selected_index())
        self.set("sorting.copy_move", tab.step_copy_move.selected_index())
        self.set("sorting.artist_mode", tab.step_artist_mode.selected_index())
        self.set("sorting.album", tab.step_album.selected_index())
        self.set("sorting.multi", tab.step_multi.selected_index())
        self.set("sorting.file_types", tab.step_file_types.selected_index())
        self.set("sorting.subfolders", tab.step_subfolders.selected_index())
        self.set("sorting.target_folder", tab.target_folder_edit.text())
        self.set("sorting.albums_folder", tab.albums_folder_edit.text())

    def apply_sorting_tab(self, tab) -> None:
        """Restore saved options into *tab*."""
        # Sort type needs special handling — it controls the target row visibility
        sort_type_idx = self.get("sorting.sort_type", -1)
        if sort_type_idx == 0:
            tab._select_sort_mode("source")
        elif sort_type_idx == 1:
            tab._select_sort_mode("target")

        _apply_step(tab.step_copy_move, self.get("sorting.copy_move", -1))
        _apply_step(tab.step_artist_mode, self.get("sorting.artist_mode", -1))

        # Album step needs special handling — index 2 shows albums folder row
        album_idx = self.get("sorting.album", -1)
        if album_idx is not None and album_idx >= 0:
            _apply_step(tab.step_album, album_idx)
            tab._animate_albums_folder_row(album_idx == 2)

        _apply_step(tab.step_multi, self.get("sorting.multi", -1))
        _apply_step(tab.step_file_types, self.get("sorting.file_types", -1))
        _apply_step(tab.step_subfolders, self.get("sorting.subfolders", -1))

        v = self.get("sorting.target_folder", "")
        if v:
            tab.target_folder_edit.setText(v)
        v = self.get("sorting.albums_folder", "")
        if v:
            tab.albums_folder_edit.setText(v)

        # Update completion indicators and summary
        tab._update_step_completion()
        tab._update_summary_text()

    # ── convenience: collect from a FeaturesTab ────────────────────────
    def collect_features_tab(self, tab) -> None:
        self.set("features.cb1", tab._cb1.isChecked())
        self.set("features.cb2", tab._cb2.isChecked())
        self.set("features.cb3", tab._cb3.isChecked())
        self.set("features.cb4", tab._cb4.isChecked())
        self.set("features.cb5", tab._cb5.isChecked())
        self.set("features.cb6", tab._cb6.isChecked())

        self.set("features.add_pos_start", tab._add_start_rb.isChecked())
        self.set("features.add_separator", tab._add_sep.text())
        self.set("features.del_chars", tab._del_chars.text())
        self.set("features.del_word", tab._del_word.text())
        self.set("features.scope_sub", tab._scope_sub.isChecked())

        self.set("features.convert_src_fmt", tab._convert_src_fmt.currentText())
        self.set("features.convert_tgt_fmt", tab._convert_tgt_fmt.currentText())
        self.set("features.convert_bitrate", tab._convert_bitrate.currentText())
        self.set("features.convert_scope_sub", tab._convert_scope_sub.isChecked())
        self.set("features.convert_delete_orig", tab._convert_delete_orig.isChecked())

        self.set("features.move_target_path", tab._move_target_path.text())
        self.set("features.move_scope_sub", tab._move_scope_sub.isChecked())
        self.set("features.del_empty_scope_sub", tab._del_empty_scope_sub.isChecked())

    def apply_features_tab(self, tab) -> None:
        _apply_cb(tab._cb1, self.get("features.cb1"))
        _apply_cb(tab._cb2, self.get("features.cb2"))
        _apply_cb(tab._cb3, self.get("features.cb3"))
        _apply_cb(tab._cb4, self.get("features.cb4"))
        _apply_cb(tab._cb5, self.get("features.cb5"))
        _apply_cb(tab._cb6, self.get("features.cb6"))

        v = self.get("features.add_pos_start")
        if v is not None:
            tab._add_start_rb.setChecked(v is True)
            tab._add_end_rb.setChecked(v is not True)

        v = self.get("features.add_separator")
        if v is not None:
            tab._add_sep.setText(str(v))

        v = self.get("features.del_chars")
        if v is not None:
            tab._del_chars.setText(str(v))

        v = self.get("features.del_word")
        if v is not None:
            tab._del_word.setText(str(v))

        v = self.get("features.scope_sub")
        if v is not None:
            tab._scope_sub.setChecked(v is True)
            tab._scope_main.setChecked(v is not True)

        v = self.get("features.convert_src_fmt")
        if v is not None:
            tab._convert_src_fmt.setCurrentText(str(v))
        v = self.get("features.convert_tgt_fmt")
        if v is not None:
            tab._convert_tgt_fmt.setCurrentText(str(v))
        v = self.get("features.convert_bitrate")
        if v is not None:
            tab._convert_bitrate.setCurrentText(str(v))
        v = self.get("features.convert_scope_sub")
        if v is not None:
            tab._convert_scope_sub.setChecked(v is True)
            tab._convert_scope_main.setChecked(v is not True)
        v = self.get("features.convert_delete_orig")
        if v is not None:
            tab._convert_delete_orig.setChecked(v is True)

        v = self.get("features.move_target_path")
        if v is not None:
            tab._move_target_path.setText(str(v))
        v = self.get("features.move_scope_sub")
        if v is not None:
            tab._move_scope_sub.setChecked(v is True)
            tab._move_scope_main.setChecked(v is not True)
        v = self.get("features.del_empty_scope_sub")
        if v is not None:
            tab._del_empty_scope_sub.setChecked(v is True)
            tab._del_empty_scope_main.setChecked(v is not True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_step(step_row, idx: int) -> None:
    """Select an option in a StepRow by index; -1 means nothing."""
    if idx is None or idx < 0:
        return
    if idx < len(step_row.opts):
        step_row._select(idx)


def _apply_cb(cb, value) -> None:
    if value is not None:
        cb.setChecked(bool(value))
