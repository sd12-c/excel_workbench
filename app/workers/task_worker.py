"""后台任务线程：统一把 log / progress 回调桥接到 Qt 信号。"""
import threading
from typing import Callable, Optional, Sequence

from PyQt5.QtCore import QThread, pyqtSignal

from app.core.errors import friendly_text, record_exception


class TaskCancelled(Exception):
    """用户主动停止任务时，由进度回调抛出的控制流异常。"""


class TaskWorker(QThread):
    log = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    ok = pyqtSignal(object)
    err = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self,
                 func: Callable,
                 args: Sequence = (),
                 kwargs: Optional[dict] = None,
                 parent=None):
        super().__init__(parent)
        self._func = func
        self._args = tuple(args)
        self._kwargs = dict(kwargs or {})
        self._cancelled = threading.Event()

    # ------------------------------------------------------------ 停止控制
    def cancel(self) -> None:
        """请求停止：当前文件处理完后，在进度回调处中断任务。"""
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    # ------------------------------------------------------------ 线程入口
    def run(self) -> None:  # noqa: D401
        try:
            if self._cancelled.is_set():
                raise TaskCancelled
            result = self._func(
                *self._args,
                log=lambda message, level="info": self.log.emit(str(message), level),
                progress=self._emit_progress,
                **self._kwargs,
            )
            if self._cancelled.is_set():
                raise TaskCancelled
            self.ok.emit(result)
        except TaskCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            # 完整 Traceback 只写入 logs/error.log，界面只收到友好的中文提示
            record_exception(exc, "后台任务")
            self.err.emit(friendly_text(exc))

    # ------------------------------------------------------------ 内部
    def _emit_progress(self, done, total) -> None:
        if self._cancelled.is_set():
            raise TaskCancelled
        self.progress.emit(int(done), int(total))
