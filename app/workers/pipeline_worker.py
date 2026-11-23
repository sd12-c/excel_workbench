"""流水线后台线程：把核心引擎的日志 / 进度 / 节点事件桥接给 Qt。"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, Mapping, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from app.core.errors import explain, record_exception
from app.core.pipeline import PipelineCancelled, run_pipeline


class PipelineWorker(QThread):
    """执行一次流水线，运行期间通过信号实时上报。

    ``event`` 里的每一项都是 JSON 字符串，由 QWebChannel 原样转发给 JS。
    """

    event = pyqtSignal(str)
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    ok = pyqtSignal(object)
    err = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self,
                 graph: Mapping[str, Any],
                 default_output_dir: str,
                 parent=None):
        super().__init__(parent)
        self._graph = dict(graph or {})
        self._default_output_dir = str(default_output_dir)
        self._cancelled = threading.Event()

    # ------------------------------------------------------------ 停止
    def cancel(self) -> None:
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    # ------------------------------------------------------------ 线程入口
    def run(self) -> None:  # noqa: D401
        try:
            result = run_pipeline(
                self._graph,
                default_output_dir=self._default_output_dir,
                emit=self._emit_event,
                log=self._emit_log,
                progress=self._emit_progress,
                is_cancelled=self._cancelled.is_set,
            )
            if self._cancelled.is_set():
                raise PipelineCancelled
            self._emit_event("run-done", result)
            self.ok.emit(result)
        except PipelineCancelled:
            self._emit_event("run-cancelled", {"message": "任务已停止"})
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "流水线画布")
            info = explain(exc)
            payload = {
                "message": info.title,
                "detail": info.detail,
                "hint": info.hint,
                "nodeId": getattr(exc, "node_id", ""),
            }
            self._emit_event("run-error", payload)
            self.err.emit(info.to_text())

    # ------------------------------------------------------------ 回调
    def _emit_event(self, name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        try:
            text = json.dumps(
                {"type": str(name), "payload": payload or {}},
                ensure_ascii=False,
            )
        except (TypeError, ValueError):
            text = json.dumps({
                "type": str(name),
                "payload": {"message": "事件数据无法序列化"},
            }, ensure_ascii=False)
        self.event.emit(text)

    def _emit_log(self, message: str, level: str = "info") -> None:
        text = str(message)
        self.log.emit(text, str(level or "info"))
        self._emit_event("log", {"message": text, "level": str(level or "info")})

    def _emit_progress(self, done: int, total: int) -> None:
        done = int(done)
        total = max(int(total), 1)
        self.progress.emit(done, total)
        self._emit_event("progress", {"done": done, "total": total})
