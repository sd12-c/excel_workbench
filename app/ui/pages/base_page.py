"""页面基类：统一任务启动 / 日志 / 进度桥接。"""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget

from app.core.errors import explain, record_exception
from app.workers.task_worker import TaskWorker


class BasePage(QWidget):
    PAGE_TITLE = ""
    PAGE_SUBTITLE = ""
    SCHEME_KEY = ""

    log_message = pyqtSignal(str, str)
    busy_changed = pyqtSignal(bool)
    progress_changed = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self.build_ui()

    # ------------------------------------------------------------ 子类实现
    def build_ui(self) -> None:
        raise NotImplementedError

    def to_scheme(self) -> dict:
        """导出当前页面的选项，供保存方案使用。"""
        return {}

    def apply_scheme(self, data: dict) -> None:
        """加载方案中的页面选项。"""

    def on_task_done(self, result) -> None:
        """任务成功后回调，子类按需覆盖。"""

    # ------------------------------------------------------------ 任务运行
    @property
    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def run_task(self, func, *args, **kwargs) -> None:
        if self.is_busy:
            self.log_message.emit("已有任务正在执行，请稍候……", "warn")
            return

        self._worker = TaskWorker(func, args, kwargs)
        self._worker.log.connect(self.log_message)
        self._worker.progress.connect(self.progress_changed)
        self._worker.ok.connect(self._on_ok)
        self._worker.err.connect(self._on_error)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.finished.connect(self._on_finished)

        self.busy_changed.emit(True)
        self._worker.start()

    def stop_task(self) -> bool:
        """请求停止当前任务；当前文件处理完后生效。"""
        if not self.is_busy:
            return False
        self._worker.cancel()
        self.log_message.emit("正在停止……（当前文件处理完成后停止）", "warn")
        return True

    # ------------------------------------------------------------ 错误处理
    def report_exception(self, exc: BaseException, action: str = "操作") -> None:
        """把异常翻译成友好中文写进运行日志，不输出原始 Traceback。"""
        record_exception(exc, action)
        info = explain(exc)
        self.log_message.emit(f"✗ {action}失败：{info.title}", "error")
        if info.detail:
            self.log_message.emit(f"    原因：{info.detail}", "error")
        if info.hint:
            self.log_message.emit(f"    建议：{info.hint}", "error")

    # ------------------------------------------------------------ 内部回调
    def _on_ok(self, result) -> None:
        self.log_message.emit("✔ 任务完成", "success")
        self.on_task_done(result)

    def _on_error(self, message: str) -> None:
        lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
        if not lines:
            lines = ["任务执行失败，请稍后重试。"]
        self.log_message.emit(f"✗ 任务失败：{lines[0]}", "error")
        for line in lines[1:]:
            self.log_message.emit(f"    {line}", "error")

    def _on_cancelled(self) -> None:
        self.log_message.emit("⏹ 任务已停止", "warn")

    def _on_finished(self) -> None:
        self.busy_changed.emit(False)
