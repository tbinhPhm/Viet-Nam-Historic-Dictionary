from __future__ import annotations

import threading
from pathlib import Path

from PySide6 import QtCore


class LocalUserJsonAutoSync(QtCore.QObject):
    def __init__(self, json_path: Path, sync_func, parent=None):
        super().__init__(parent)
        self.json_path = Path(json_path)
        self._sync_func = sync_func
        self._last_mtime_ns: int | None = None

        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._sync_now)

        self._poll = QtCore.QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._check)

    def start(self) -> None:
        self._check()
        self._poll.start()

    def _mtime_ns(self) -> int | None:
        try:
            return self.json_path.stat().st_mtime_ns
        except Exception:
            return None

    @QtCore.Slot()
    def _check(self) -> None:
        mtime = self._mtime_ns()
        if mtime is None:
            return
        if self._last_mtime_ns is None:
            self._last_mtime_ns = mtime
            return
        if mtime != self._last_mtime_ns:
            self._last_mtime_ns = mtime
            self._debounce.start(1500)

    def _sync_now(self) -> None:
        def worker():
            try:
                self._sync_func(self.json_path)
            except Exception:
                return

        threading.Thread(target=worker, daemon=True).start()

