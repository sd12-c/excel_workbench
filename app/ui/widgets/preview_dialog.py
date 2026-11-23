"""通用数据预览对话框：展示 Excel / CSV 的前 20 行。"""
import os
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFrame,
                             QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                             QPushButton, QSizePolicy, QTableWidget,
                             QTableWidgetItem, QVBoxLayout)

from app.core.errors import explain, record_exception
from app.core.preview import PREVIEW_ROWS, PreviewData, read_preview
from app.ui.widgets.backdrop import SoftBackdrop
from app.ui.widgets.brand import BrandLogo


class PreviewDialog(QDialog):
    """只读预览：表头 + 前 20 行，支持切换工作表。"""

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._loading = False
        self.setObjectName("PreviewDialog")
        self.setWindowTitle(f"数据预览 - {os.path.basename(path)}")
        self.resize(960, 600)
        self.setMinimumSize(680, 440)
        self._build_ui()
        self._load()

    # ------------------------------------------------------------ 构建界面
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        backdrop = SoftBackdrop(self)
        backdrop.setObjectName("PreviewBackdrop")
        outer.addWidget(backdrop)
        layout = QVBoxLayout(backdrop)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(11)
        logo = BrandLogo(32)
        head.addWidget(logo, 0, Qt.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(1)
        title = QLabel("数据预览")
        title.setObjectName("PreviewTitle")
        self.file_label = QLabel(os.path.basename(self._path))
        self.file_label.setObjectName("PreviewFilename")
        self.file_label.setToolTip(self._path)
        self.file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        title_box.addWidget(title)
        title_box.addWidget(self.file_label)
        head.addLayout(title_box, 1)

        readonly = QLabel("只读")
        readonly.setObjectName("ReadonlyBadge")
        head.addWidget(readonly, 0, Qt.AlignVCenter)

        self.sheet_label = QLabel("工作表")
        self.sheet_label.setObjectName("FieldLabel")
        self.combo_sheet = QComboBox()
        self.combo_sheet.setMinimumWidth(180)
        self.combo_sheet.currentTextChanged.connect(self._on_sheet_changed)
        head.addWidget(self.sheet_label)
        head.addWidget(self.combo_sheet)
        layout.addLayout(head)

        self.info_label = QLabel(f"正在读取前 {PREVIEW_ROWS} 行……")
        self.info_label.setObjectName("PreviewInfo")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        panel = QFrame()
        panel.setObjectName("GlassPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(6, 6, 6, 6)
        panel_layout.setSpacing(0)

        self.table = QTableWidget()
        self.table.setObjectName("PreviewTable")
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        panel_layout.addWidget(self.table)
        layout.addWidget(panel, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        privacy = QLabel("仅本地预览 · 不会修改原文件")
        privacy.setObjectName("HintLabel")
        bottom.addWidget(privacy)
        bottom.addStretch(1)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setObjectName("GhostButton")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        bottom.addWidget(self.btn_close)
        layout.addLayout(bottom)

    # ------------------------------------------------------------ 数据加载
    def _load(self, sheet_name: Optional[str] = None) -> None:
        try:
            data = read_preview(self._path, sheet_name)
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return

        self._loading = True
        self.combo_sheet.clear()
        self.combo_sheet.addItems(data.sheet_names)
        if data.sheet_name:
            self.combo_sheet.setCurrentText(data.sheet_name)
        has_sheets = bool(data.sheet_names)
        self.sheet_label.setVisible(has_sheets)
        self.combo_sheet.setVisible(has_sheets)
        self.combo_sheet.setEnabled(len(data.sheet_names) > 1)
        self._loading = False

        self._apply(data)

    def _apply(self, data: PreviewData) -> None:
        self.table.clear()
        self.table.setColumnCount(len(data.columns))
        self.table.setHorizontalHeaderLabels(data.columns)
        self.table.setRowCount(len(data.rows))
        for row_index, row in enumerate(data.rows):
            for column_index, text in enumerate(row):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row_index, column_index, item)

        self.table.resizeColumnsToContents()
        for index in range(self.table.columnCount()):
            width = self.table.columnWidth(index)
            self.table.setColumnWidth(index, min(max(width + 8, 90), 260))
        self.table.scrollToTop()

        prefix = f"工作表「{data.sheet_name}」 · " if data.sheet_name else ""
        self.info_label.setText(
            f"{prefix}共 {len(data.columns)} 列 · 当前显示 {len(data.rows)} 行"
            f"（最多前 {PREVIEW_ROWS} 行，仅预览不会修改文件）")

    def _show_error(self, exc: BaseException) -> None:
        record_exception(exc, "预览文件")
        info = explain(exc)
        self.info_label.setText(f"无法预览：{info.title}")
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.combo_sheet.clear()
        QMessageBox.warning(self, "无法预览", info.to_text())

    def _on_sheet_changed(self, sheet_name: str) -> None:
        if self._loading or not sheet_name:
            return
        self._load(sheet_name)
