"""表单通用组件。"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QVBoxLayout, QWidget)

from app.config import ensure_output_dir
from app.core.common import normalize_path

def default_output_path(filename: str) -> str:
    """默认输出路径：项目根目录下的 out_put 文件夹内。"""
    folder = ensure_output_dir()
    return os.path.join(folder, filename)


class Card(QFrame):
    """白色圆角卡片容器。"""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 14, 18, 16)
        self._layout.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            self._layout.addWidget(label)

    @property
    def body(self) -> QVBoxLayout:
        return self._layout

    def add(self, widget: QWidget, stretch: int = 0):
        self._layout.addWidget(widget, stretch)

    def add_layout(self, layout):
        self._layout.addLayout(layout)


class PathPicker(QWidget):
    """带浏览按钮的路径选择框。"""

    def __init__(self, mode: str = "dir", placeholder: str = "", parent=None):
        super().__init__(parent)
        self.mode = mode
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.editingFinished.connect(self._normalize_edit)
        self.button = QPushButton("浏览")
        self.button.setObjectName("GhostButton")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self._browse)

        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def _browse(self) -> None:
        current = normalize_path(self.edit.text())
        if self.mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "选择输出目录", current)
        elif self.mode == "save":
            path, _ = QFileDialog.getSaveFileName(
                self, "选择输出文件", current or default_output_path("输出.xlsx"),
                "Excel 文件 (*.xlsx)")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", current)
        if path:
            self.set_path(path)

    def path(self) -> str:
        return normalize_path(self.edit.text())

    def set_path(self, path: str) -> None:
        self.edit.setText(normalize_path(path))

    def _normalize_edit(self) -> None:
        normalized = normalize_path(self.edit.text())
        if normalized != self.edit.text():
            self.edit.setText(normalized)


def labeled_row(label_text: str, widget: QWidget, label_width: int = 96) -> QWidget:
    """左侧标签 + 右侧控件的一行布局。"""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    label = QLabel(label_text)
    label.setObjectName("FieldLabel")
    label.setFixedWidth(label_width)
    layout.addWidget(label)
    layout.addWidget(widget, 1)
    return row