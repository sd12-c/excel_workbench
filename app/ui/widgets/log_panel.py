"""底部日志面板 + 全局进度条 + 停止按钮。"""
import datetime
from html import escape

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QTextEdit, QVBoxLayout, QWidget)

from app.core.common import quote_path
from app.core.errors import explain, record_exception

_COLORS = {
    "info": "#cfd6e6",
    "success": "#5ddc9a",
    "warn": "#ffc46b",
    "error": "#ff7f7f",
}


class LogPanel(QWidget):
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LogPanel")
        self._stopping = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setSpacing(10)

        title = QLabel("运行日志")
        title.setObjectName("CardTitle")
        head.addWidget(title)

        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("HintLabel")
        self.status_label.setMinimumWidth(160)
        head.addWidget(self.status_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        head.addWidget(self.progress, 1)

        self.btn_stop = QPushButton("停止")
        self.btn_stop.setObjectName("StopButton")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setToolTip("停止当前任务（会在当前文件处理完成后停止）")
        head.addWidget(self.btn_stop)

        self.btn_clear = QPushButton("清空")
        self.btn_export = QPushButton("导出日志")
        for button in (self.btn_clear, self.btn_export):
            button.setObjectName("GhostButton")
            button.setCursor(Qt.PointingHandCursor)
            head.addWidget(button)

        layout.addLayout(head)

        self.view = QTextEdit()
        self.view.setObjectName("LogView")
        self.view.setReadOnly(True)
        layout.addWidget(self.view, 1)

        self.btn_stop.clicked.connect(self.stop_requested.emit)
        self.btn_clear.clicked.connect(self.view.clear)
        self.btn_export.clicked.connect(self._export)

    # ------------------------------------------------------------ public
    def append(self, message: str, level: str = "info") -> None:
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        color = _COLORS.get(level, _COLORS["info"])
        html = (f'<span style="color:#5c6a85">[{stamp}]</span> '
                f'<span style="color:{color}">{escape(str(message))}</span>')
        self.view.append(html)
        self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum())

    def set_busy(self, busy: bool) -> None:
        """任务开始 / 全部结束时切换停止按钮与状态文字。"""
        self._stopping = False
        self.btn_stop.setEnabled(busy)
        self.status_label.setText("正在处理…" if busy else "就绪")

    def set_progress(self, done: int, total: int) -> None:
        total = max(int(total), 1)
        self.progress.setMaximum(total)
        self.progress.setValue(int(done))
        if not self._stopping:
            self.status_label.setText(f"正在处理文件 {done}/{total}")

    def set_stopping(self) -> None:
        """用户已点击停止，等待当前文件处理完。"""
        self._stopping = True
        self.btn_stop.setEnabled(False)
        self.status_label.setText("正在停止…（当前文件完成后停止）")

    def reset_progress(self) -> None:
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        if not self._stopping:
            self.status_label.setText("就绪")

    # ----------------------------------------------------------- internal
    def _export(self) -> None:
        if not self.view.toPlainText().strip():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出日志", "excel_workbench_log.txt", "文本文件 (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(self.view.toPlainText())
            self.append(f"✔ 日志已导出到：{quote_path(path)}", "success")
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "导出日志")
            info = explain(exc)
            self.append(f"✗ 导出日志失败：{info.title}", "error")
            if info.detail:
                self.append(f"    原因：{info.detail}", "error")
            if info.hint:
                self.append(f"    建议：{info.hint}", "error")
