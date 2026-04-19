"""
Undo Manager — records file-system operations so they can be reversed.

Every user-visible action (sort, rename, delete duplicates, etc.) is wrapped in
a *batch*.  Undoing a batch reverses **all** its atomic steps in reverse order.

Supported atomic action types
─────────────────────────────
  copy      → undo by deleting the destination file
  move      → undo by moving the file back
  rename    → undo by renaming back (same as move, kept for clarity)
  delete    → file is moved to a hidden trash folder; undo restores it
  mkdir     → undo by removing the directory (only if it is still empty)
  rmdir     → undo by recreating the directory
  convert   → new file created + optional source deleted; undo removes new & restores source
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from shared import app_data_path

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class UndoAction:
    action_type: str          # copy | move | rename | delete | mkdir | rmdir | convert
    src: str = ""             # original source path
    dst: str = ""             # destination path
    trash_path: str = ""      # path in trash (for delete actions)
    extra: dict = field(default_factory=dict)


@dataclass
class UndoBatch:
    batch_id: str
    description: str
    timestamp: float
    actions: list[UndoAction] = field(default_factory=list)

    # ── serialisation helpers ──────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "description": self.description,
            "timestamp": self.timestamp,
            "actions": [asdict(a) for a in self.actions],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "UndoBatch":
        actions = [UndoAction(**a) for a in d.get("actions", [])]
        return cls(
            batch_id=d["batch_id"],
            description=d["description"],
            timestamp=d["timestamp"],
            actions=actions,
        )


# ---------------------------------------------------------------------------
# UndoManager
# ---------------------------------------------------------------------------

_HISTORY_FILE = "undo_history.json"
_TRASH_DIR_NAME = ".undo_trash"
_MAX_BATCHES = 50          # keep last N batches to avoid infinite growth


class UndoManager:
    """Singleton-style manager shared by all tabs."""

    def __init__(self) -> None:
        self._batches: list[UndoBatch] = []
        self._current_batch: Optional[UndoBatch] = None

        # Trash lives next to the app data files
        self._trash_root = os.path.join(tempfile.gettempdir(), _TRASH_DIR_NAME)
        os.makedirs(self._trash_root, exist_ok=True)

        self._load_history()

    # ── properties ─────────────────────────────────────────────────────
    @property
    def can_undo(self) -> bool:
        return len(self._batches) > 0

    @property
    def batches(self) -> list[UndoBatch]:
        return list(self._batches)

    @property
    def last_batch_description(self) -> str:
        if self._batches:
            return self._batches[-1].description
        return ""

    # ── batch lifecycle ────────────────────────────────────────────────
    def begin_batch(self, description: str) -> None:
        self._current_batch = UndoBatch(
            batch_id=uuid.uuid4().hex,
            description=description,
            timestamp=time.time(),
        )

    def end_batch(self) -> None:
        if self._current_batch is None:
            return
        if self._current_batch.actions:
            self._batches.append(self._current_batch)
            # Prune old batches
            if len(self._batches) > _MAX_BATCHES:
                removed = self._batches[: len(self._batches) - _MAX_BATCHES]
                self._batches = self._batches[-_MAX_BATCHES:]
                # Clean trash for removed batches
                for batch in removed:
                    self._clean_trash_for_batch(batch)
            self._save_history()
        self._current_batch = None

    def discard_batch(self) -> None:
        """Cancel the current batch without recording."""
        self._current_batch = None

    # ── recording helpers ──────────────────────────────────────────────
    def record_copy(self, src: str, dst: str) -> None:
        self._record("copy", src=src, dst=dst)

    def record_move(self, src: str, dst: str) -> None:
        self._record("move", src=src, dst=dst)

    def record_rename(self, src: str, dst: str) -> None:
        self._record("rename", src=src, dst=dst)

    def record_mkdir(self, path: str) -> None:
        self._record("mkdir", dst=path)

    def record_rmdir(self, path: str) -> None:
        self._record("rmdir", dst=path)

    def record_convert(self, src: str, dst: str, source_deleted: bool = False) -> None:
        self._record("convert", src=src, dst=dst,
                      extra={"source_deleted": source_deleted})

    def safe_delete(self, path: str) -> bool:
        """Move *path* into the trash folder so it can be restored later.
        Returns True on success."""
        if not os.path.isfile(path):
            return False
        batch_id = self._current_batch.batch_id if self._current_batch else "orphan"
        trash_dir = os.path.join(self._trash_root, batch_id)
        os.makedirs(trash_dir, exist_ok=True)
        # Preserve uniqueness — prefix with a uuid fragment
        trash_name = f"{uuid.uuid4().hex[:8]}_{os.path.basename(path)}"
        trash_path = os.path.join(trash_dir, trash_name)
        try:
            shutil.move(path, trash_path)
        except OSError:
            return False
        self._record("delete", src=path, trash_path=trash_path)
        return True

    def _record(self, action_type: str, **kwargs) -> None:
        if self._current_batch is None:
            return
        self._current_batch.actions.append(UndoAction(action_type=action_type, **kwargs))

    # ── undo ───────────────────────────────────────────────────────────
    def undo_last(self) -> tuple[bool, str]:
        """Undo the most-recent batch.  Returns (success, message)."""
        if not self._batches:
            return False, "אין פעולות לביטול"
        batch = self._batches.pop()
        ok, msg = self._undo_batch(batch)
        self._save_history()
        return ok, msg

    def undo_batch_by_id(self, batch_id: str) -> tuple[bool, str]:
        idx = None
        for i, b in enumerate(self._batches):
            if b.batch_id == batch_id:
                idx = i
                break
        if idx is None:
            return False, "הפעולה לא נמצאה"
        batch = self._batches.pop(idx)
        ok, msg = self._undo_batch(batch)
        self._save_history()
        return ok, msg

    def _undo_batch(self, batch: UndoBatch) -> tuple[bool, str]:
        errors: list[str] = []
        restored = 0
        for action in reversed(batch.actions):
            try:
                self._undo_action(action)
                restored += 1
            except Exception as exc:
                errors.append(f"{action.action_type} {action.src or action.dst}: {exc}")
        # Clean trash for this batch
        self._clean_trash_for_batch(batch)
        total = len(batch.actions)
        if errors:
            return False, (
                f"בוטלו {restored}/{total} פעולות.\n"
                + "\n".join(errors[:10])
            )
        return True, f"בוטלו {total} פעולות בהצלחה — {batch.description}"

    def _undo_action(self, action: UndoAction) -> None:
        t = action.action_type
        if t == "copy":
            # Remove the copied file
            if os.path.isfile(action.dst):
                os.remove(action.dst)

        elif t in ("move", "rename"):
            # Move / rename back
            if os.path.exists(action.dst):
                dest_dir = os.path.dirname(action.src)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                shutil.move(action.dst, action.src)

        elif t == "delete":
            # Restore from trash
            if os.path.isfile(action.trash_path):
                dest_dir = os.path.dirname(action.src)
                if dest_dir:
                    os.makedirs(dest_dir, exist_ok=True)
                shutil.move(action.trash_path, action.src)

        elif t == "mkdir":
            # Remove the directory if it is empty
            d = action.dst
            if os.path.isdir(d):
                try:
                    os.rmdir(d)
                except OSError:
                    pass  # not empty → leave it

        elif t == "rmdir":
            # Recreate the directory
            os.makedirs(action.dst, exist_ok=True)

        elif t == "convert":
            # Remove converted file; restore source if it was deleted
            if os.path.isfile(action.dst):
                os.remove(action.dst)
            # Source restoration is handled by a paired "delete" action if source_deleted

    # ── trash cleanup ──────────────────────────────────────────────────
    def _clean_trash_for_batch(self, batch: UndoBatch) -> None:
        trash_dir = os.path.join(self._trash_root, batch.batch_id)
        if os.path.isdir(trash_dir):
            shutil.rmtree(trash_dir, ignore_errors=True)

    def clear_all(self) -> None:
        """Clear all undo history and trash."""
        self._batches.clear()
        if os.path.isdir(self._trash_root):
            shutil.rmtree(self._trash_root, ignore_errors=True)
        os.makedirs(self._trash_root, exist_ok=True)
        self._save_history()

    # ── persistence ────────────────────────────────────────────────────
    def _history_path(self) -> str:
        return app_data_path(_HISTORY_FILE)

    def _save_history(self) -> None:
        data = [b.to_dict() for b in self._batches]
        try:
            with open(self._history_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_history(self) -> None:
        path = self._history_path()
        if not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._batches = [UndoBatch.from_dict(d) for d in data]
        except Exception:
            self._batches = []
