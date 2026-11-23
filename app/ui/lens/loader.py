"""后台读取 Excel 表头缩略，避免拖入大文件时界面卡顿。"""
from __future__ import annotations

from typing import Iterable, List

from PyQt5.QtCore import QThread, pyqtSignal

from app.core.errors import explain, record_exception
from app.core.preview import read_preview


class PreviewLoader(QThread):
    """逐文件读取前几行与表头，并通过信号增量刷新卡片。"""

    item_ready = pyqtSignal(int, str, object)
    batch_finished = pyqtSignal(int)

    def __init__(self, token: int, paths: Iterable[str], parent=None):
        super().__init__(parent)
        self._token = int(token)
        self._paths: List[str] = list(paths)
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True
        self.requestInterruption()

    def run(self) -> None:  # noqa: D401
        for path in self._paths:
            if self._stopped or self.isInterruptionRequested():
                break
            try:
                preview = read_preview(path, rows=3)
                payload = {
                    "columns": list(preview.columns),
                    "rows": [list(row) for row in preview.rows],
                    "sheets": list(preview.sheet_names),
                    "error": "",
                }
            except Exception as exc:  # noqa: BLE001
                record_exception(exc, "读取表头预览")
                payload = {
                    "columns": [],
                    "rows": [],
                    "sheets": [],
                    "error": explain(exc).title,
                }
            if self._stopped or self.isInterruptionRequested():
                break
            self.item_ready.emit(self._token, path, payload)
        self.batch_finished.emit(self._token)
