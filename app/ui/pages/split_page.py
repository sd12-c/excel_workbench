"""拆分工作表页面。"""
import os

import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QRadioButton,
                             QScrollArea, QVBoxLayout, QWidget)

from app.core.splitter import (DEFAULT_FILENAME_TEMPLATE, split_by_column,
                               validate_filename_template)
from app.ui.scheme import scheme_bool, scheme_str
from app.ui.widgets.file_list import FileListWidget
from app.ui.widgets.form_helpers import (Card, PathPicker, default_output_path,
                                          labeled_row)

from .base_page import BasePage


class SplitPage(BasePage):
    PAGE_TITLE = "拆分工作表"
    PAGE_SUBTITLE = "按指定列分组拆分，支持自定义文件名模板、跳过空分组"
    SCHEME_KEY = "split"

    def build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        container = QWidget()
        container.setObjectName("ScrollBody")
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        files_card = Card("源文件")
        self.file_list = FileListWidget("拖拽 Excel 文件 / 文件夹到此处")
        files_card.add(self.file_list, 1)
        root.addWidget(files_card, 1)

        option_card = Card("拆分选项")
        option_card.body.setSpacing(8)
        option_card.body.setContentsMargins(16, 12, 16, 12)

        column_row = QWidget()
        column_layout = QHBoxLayout(column_row)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(8)
        self.combo_column = QComboBox()
        self.combo_column.setEditable(True)
        self.combo_column.setMinimumWidth(220)
        self.combo_column.lineEdit().setPlaceholderText("用于分组的列名")
        self.btn_load_columns = QPushButton("读取列名")
        self.btn_load_columns.setObjectName("GhostButton")
        self.btn_load_columns.setCursor(Qt.PointingHandCursor)
        self.btn_load_columns.clicked.connect(self._load_columns)
        column_layout.addWidget(self.combo_column, 1)
        column_layout.addWidget(self.btn_load_columns)
        option_card.add(labeled_row("分组列", column_row))

        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(24)
        self.radio_file = QRadioButton("每个分组输出一个独立文件")
        self.radio_file.setChecked(True)
        self.radio_sheet = QRadioButton("每个分组输出为一个工作表")
        mode_layout.addWidget(self.radio_file)
        mode_layout.addWidget(self.radio_sheet)
        mode_layout.addStretch(1)
        option_card.add(labeled_row("拆分方式", mode_row))

        self.edit_filename_template = QLineEdit(DEFAULT_FILENAME_TEMPLATE)
        self.edit_filename_template.setPlaceholderText("例如：{分组列值}_数据.xlsx")
        self.edit_filename_template.setToolTip(
            "可用占位符：{分组列值}、{原文件名}、{工作表名}；"
            "多工作表且模板未包含 {工作表名} 时，会自动追加工作表名")
        self.template_row = labeled_row("文件名模板", self.edit_filename_template)
        option_card.add(self.template_row)

        self.cb_filter_empty = QCheckBox("过滤空分组（不生成空文件）")
        self.cb_filter_empty.setChecked(True)
        self.cb_filter_empty.setToolTip("分组列为空值或空白时自动跳过")
        option_card.add(self.cb_filter_empty)

        self.output_picker = PathPicker("dir", "选择拆分结果的输出目录")
        self.output_picker.set_path(default_output_path("拆分输出"))
        option_card.add(labeled_row("输出目录", self.output_picker))
        root.addWidget(option_card)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_run = QPushButton("开始拆分")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setMinimumWidth(150)
        self.btn_run.clicked.connect(self._run)
        bottom.addWidget(self.btn_run)

        scroll.setWidget(container)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)
        page_layout.addWidget(scroll, 1)
        page_layout.addLayout(bottom)

        self.radio_file.toggled.connect(self._update_template_state)
        self._update_template_state()
        self.busy_changed.connect(self._on_busy)
        self.file_list.changed.connect(self._on_files_changed)

    # ------------------------------------------------------------ 内部
    def _on_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_run.setText("拆分中…" if busy else "开始拆分")

    def _update_template_state(self, *_args) -> None:
        self.template_row.setEnabled(self.radio_file.isChecked())

    def to_scheme(self) -> dict:
        return {
            "column": self.combo_column.currentText(),
            "mode": "file" if self.radio_file.isChecked() else "sheet",
            "filename_template": self.edit_filename_template.text(),
            "filter_empty": self.cb_filter_empty.isChecked(),
            "output": self.output_picker.path(),
        }

    def apply_scheme(self, data: dict) -> None:
        self.combo_column.setCurrentText(
            scheme_str(data, "column", self.combo_column.currentText()))
        file_mode = scheme_str(data, "mode", "file") != "sheet"
        self.radio_file.setChecked(file_mode)
        self.radio_sheet.setChecked(not file_mode)
        self.edit_filename_template.setText(
            scheme_str(data, "filename_template", DEFAULT_FILENAME_TEMPLATE))
        self.cb_filter_empty.setChecked(
            scheme_bool(data, "filter_empty", True))
        self.output_picker.set_path(
            scheme_str(data, "output", self.output_picker.path()))
        self._update_template_state()

    def _on_files_changed(self, files) -> None:
        """导入 / 移除文件后自动刷新列名，用户无需手动输入。"""
        if files:
            self._load_columns()

    def _load_columns(self) -> None:
        files = self.file_list.files()
        if not files:
            self.log_message.emit("请先添加源文件", "warn")
            return

        path = self._current_source_file(files)
        try:
            frame = pd.read_excel(path, sheet_name=0, nrows=5)
        except Exception as exc:  # noqa: BLE001
            self.report_exception(exc, "读取列名")
            return

        columns = list(dict.fromkeys(str(column) for column in frame.columns))
        current = self.combo_column.currentText()
        self.combo_column.blockSignals(True)
        self.combo_column.clear()
        self.combo_column.addItems(columns)
        if current:
            self.combo_column.setCurrentText(current)
        self.combo_column.blockSignals(False)
        self.log_message.emit(
            f"已读取 {len(columns)} 个列名"
            f"（{os.path.basename(path)} · 第一张工作表）", "success")

    def _current_source_file(self, files):
        """优先使用列表中选中的文件，否则使用第一个文件。"""
        selected = self.file_list.list.selectedItems()
        if selected:
            path = selected[0].data(Qt.UserRole)
            if path in files:
                return path
        return files[0]

    def _run(self) -> None:
        files = self.file_list.files()
        if not files:
            self.log_message.emit("请先添加需要拆分的文件", "warn")
            return
        column = self.combo_column.currentText().strip()
        if not column:
            self.log_message.emit("请填写或选择用于分组的列名", "warn")
            return
        output = self.output_picker.path()
        if not output:
            self.log_message.emit("请选择输出目录", "warn")
            return

        mode = "file" if self.radio_file.isChecked() else "sheet"
        template = DEFAULT_FILENAME_TEMPLATE
        if mode == "file":
            try:
                template = validate_filename_template(
                    self.edit_filename_template.text())
            except ValueError as exc:
                self.log_message.emit(f"✗ {exc}", "warn")
                return
            self.edit_filename_template.setText(template)

        self.run_task(
            split_by_column, files, column, output,
            mode=mode,
            skip_empty_groups=self.cb_filter_empty.isChecked(),
            filename_template=template,
        )