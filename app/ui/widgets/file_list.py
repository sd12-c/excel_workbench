"""可拖拽的文件列表组件。"""
import os
from typing import Iterable, List, Optional, Set

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel,
                             QListWidget, QListWidgetItem, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)


class _DropListWidget(QListWidget):
    paths_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("FileList")
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setMinimumHeight(170)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.paths_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class FileListWidget(QWidget):
    """拖拽 / 按钮两种方式添加文件的列表。"""

    changed = pyqtSignal(list)

    def __init__(self,
                 hint: str = "拖拽文件或文件夹到此处",
                 extensions: Optional[Iterable[str]] = None,
                 parent=None):
        super().__init__(parent)
        self._extensions: Set[str] = set(extensions or (".xlsx", ".xls", ".xlsm"))
        self._paths: List[str] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.list = _DropListWidget()
        self.list.setToolTip(hint)
        self.list.paths_dropped.connect(self.add_paths)
        layout.addWidget(self.list, 1)

        bar = QHBoxLayout()
        bar.setSpacing(8)

        self.btn_add_files = QPushButton("添加文件")
        self.btn_add_dir = QPushButton("添加文件夹")
        self.btn_preview = QPushButton("预览")
        self.btn_preview.setToolTip("预览选中文件的前 20 行（双击文件同样可预览）")
        self.btn_remove = QPushButton("移除选中")
        self.btn_clear = QPushButton("清空")
        for button in (self.btn_add_files, self.btn_add_dir,
                       self.btn_preview, self.btn_remove, self.btn_clear):
            button.setObjectName("GhostButton")
            button.setCursor(Qt.PointingHandCursor)
            bar.addWidget(button)

        self.count_label = QLabel("0 个文件")
        self.count_label.setObjectName("HintLabel")
        bar.addStretch(1)
        bar.addWidget(self.count_label)
        layout.addLayout(bar)

        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_dir.clicked.connect(self._pick_folder)
        self.btn_preview.clicked.connect(self._preview_selected)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear.clicked.connect(self.clear)
        self.list.itemDoubleClicked.connect(self._preview_item)

    # ---------------------------------------------------------------- API
    def files(self) -> List[str]:
        return list(self._paths)

    def set_extensions(self, extensions: Iterable[str]) -> None:
        self._extensions = set(extensions)

    def add_paths(self, paths: Iterable[str]) -> None:
        added = 0
        for raw in paths:
            path = os.path.abspath(raw)
            if os.path.isdir(path):
                for name in sorted(os.listdir(path)):
                    candidate = os.path.join(path, name)
                    if os.path.isfile(candidate) and self._accept(candidate) \
                            and candidate not in self._paths:
                        self._paths.append(candidate)
                        added += 1
            elif os.path.isfile(path) and self._accept(path) and path not in self._paths:
                self._paths.append(path)
                added += 1
        if added:
            self._refresh()
        else:
            self._refresh()

    def clear(self) -> None:
        if not self._paths:
            return
        self._paths.clear()
        self._refresh()

    # ------------------------------------------------------------ internal
    def _accept(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in self._extensions

    def _pick_files(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        patterns = " ".join(f"*{ext}" for ext in sorted(self._extensions))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "", f"支持的文件 ({patterns})")
        if paths:
            self.add_paths(paths)

    def _pick_folder(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            self.add_paths([folder])

    # ------------------------------------------------------------ 预览
    def _preview_selected(self) -> None:
        selected = self.list.selectedItems()
        if selected:
            path = selected[0].data(Qt.UserRole)
        else:
            path = self._paths[0] if self._paths else ""
        if not path:
            QMessageBox.information(self, "预览", "请先添加需要预览的文件。")
            return
        self._open_preview(path)

    def _preview_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self._open_preview(path)

    def _open_preview(self, path: str) -> None:
        from app.core.preview import is_previewable
        if not is_previewable(path):
            QMessageBox.information(
                self, "暂不支持预览",
                "当前仅支持预览 Excel（.xlsx / .xls / .xlsm）和 CSV 文件。")
            return
        from .preview_dialog import PreviewDialog
        PreviewDialog(path, self).exec_()

    def _remove_selected(self) -> None:
        selected = {item.data(Qt.UserRole) for item in self.list.selectedItems()}
        if not selected:
            return
        self._paths = [p for p in self._paths if p not in selected]
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        for path in self._paths:
            item = QListWidgetItem(os.path.basename(path))
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.list.addItem(item)
        self.count_label.setText(f"{len(self._paths)} 个文件")
        self.changed.emit(list(self._paths))