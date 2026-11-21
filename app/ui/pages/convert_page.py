"""格式转换页面。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame,
                             QHBoxLayout, QPushButton, QRadioButton,
                             QScrollArea, QVBoxLayout, QWidget)

from app.core.converter import csv_to_excel, excel_to_csv
from app.ui.scheme import scheme_bool, scheme_str
from app.ui.widgets.file_list import FileListWidget
from app.ui.widgets.form_helpers import (Card, PathPicker, default_output_path,
                                          labeled_row)

from .base_page import BasePage


class ConvertPage(BasePage):
    PAGE_TITLE = "格式转换"
    PAGE_SUBTITLE = "CSV ↔ Excel 互转（CSV 支持 UTF-8 / GBK 编码选择）"
    SCHEME_KEY = "convert"

    MODES = [
        ("csv2excel", "CSV → Excel", (".csv",), "转换输出"),
        ("excel2csv", "Excel → CSV", (".xlsx", ".xls", ".xlsm"), "转换输出"),
    ]

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

        mode_card = Card("转换类型")
        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(24)

        self.mode_group = QButtonGroup(self)
        self.mode_buttons = []
        for index, (key, text, _ext, _out) in enumerate(self.MODES):
            button = QRadioButton(text)
            if index == 0:
                button.setChecked(True)
            self.mode_group.addButton(button, index)
            self.mode_buttons.append(button)
            mode_layout.addWidget(button)
        mode_layout.addStretch(1)
        mode_card.add(mode_row)
        root.addWidget(mode_card)

        files_card = Card("源文件")
        self.file_list = FileListWidget("拖拽文件 / 文件夹到此处", extensions=(".csv",))
        files_card.add(self.file_list, 1)
        root.addWidget(files_card, 1)

        option_card = Card("输出设置")
        option_card.body.setSpacing(8)
        option_card.body.setContentsMargins(16, 12, 16, 12)
        self.cb_all_sheets = QCheckBox("处理工作簿中的所有工作表")
        self.cb_all_sheets.setChecked(True)
        option_card.add(self.cb_all_sheets)

        self.combo_encoding = QComboBox()
        self.combo_encoding.addItem("自动识别（推荐）", "auto")
        self.combo_encoding.addItem("UTF-8", "utf-8")
        self.combo_encoding.addItem("GBK", "gbk")
        self.combo_encoding.setToolTip(
            "国内 Excel 导出的 CSV 常见为 GBK；出现乱码时请改选 GBK")
        self.encoding_row = labeled_row("CSV 输入编码", self.combo_encoding)
        option_card.add(self.encoding_row)

        self.output_picker = PathPicker("dir", "选择输出目录")
        self.output_picker.set_path(default_output_path("转换输出"))
        option_card.add(labeled_row("输出目录", self.output_picker))
        root.addWidget(option_card)

        scroll.setWidget(container)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(14)
        page_layout.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_run = QPushButton("开始转换")
        self.btn_run.setObjectName("PrimaryButton")
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setMinimumWidth(150)
        self.btn_run.clicked.connect(self._run)
        bottom.addWidget(self.btn_run)
        page_layout.addLayout(bottom)

        self.mode_group.buttonClicked.connect(self._on_mode_changed)
        self.busy_changed.connect(self._on_busy)
        self._on_mode_changed()

    # ------------------------------------------------------------ 内部
    def _current_mode(self):
        index = self.mode_group.checkedId()
        if index < 0:
            index = 0
        return self.MODES[index]

    def _on_mode_changed(self) -> None:
        self._apply_mode_ui(self._current_mode()[0], reset_files=True)

    def _apply_mode_ui(self, key: str, reset_files: bool) -> None:
        for index, (mode_key, _text, extensions, default_name) in enumerate(self.MODES):
            if mode_key != key:
                continue
            self.mode_buttons[index].setChecked(True)
            self.file_list.set_extensions(extensions)
            if reset_files:
                self.file_list.clear()
                self.output_picker.set_path(default_output_path(default_name))
            self.cb_all_sheets.setEnabled(key != "csv2excel")
            self.encoding_row.setVisible(key == "csv2excel")
            return

    def to_scheme(self) -> dict:
        return {
            "mode": self._current_mode()[0],
            "all_sheets": self.cb_all_sheets.isChecked(),
            "encoding": self.combo_encoding.currentData(),
            "output": self.output_picker.path(),
        }

    def apply_scheme(self, data: dict) -> None:
        valid_modes = {key for key, _text, _ext, _out in self.MODES}
        mode = scheme_str(data, "mode", "csv2excel")
        if mode not in valid_modes:
            mode = "csv2excel"

        current_mode = self._current_mode()[0]
        self._apply_mode_ui(mode, reset_files=(mode != current_mode))
        self.cb_all_sheets.setChecked(scheme_bool(data, "all_sheets", True))

        encoding = scheme_str(data, "encoding", "auto")
        encoding_index = self.combo_encoding.findData(encoding)
        self.combo_encoding.setCurrentIndex(
            encoding_index if encoding_index >= 0 else 0)

        self.output_picker.set_path(
            scheme_str(data, "output", self.output_picker.path()))

    def _on_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_run.setText("转换中…" if busy else "开始转换")

    def _run(self) -> None:
        files = self.file_list.files()
        if not files:
            self.log_message.emit("请先添加需要转换的文件", "warn")
            return
        output = self.output_picker.path()
        if not output:
            self.log_message.emit("请选择输出目录", "warn")
            return

        key, text, _ext, _name = self._current_mode()
        self.log_message.emit(f"开始执行：{text}（{len(files)} 个文件）", "info")

        if key == "csv2excel":
            self.run_task(
                csv_to_excel, files, output,
                encoding=self.combo_encoding.currentData(),
            )
        else:
            self.run_task(excel_to_csv, files, output,
                          all_sheets=self.cb_all_sheets.isChecked())
