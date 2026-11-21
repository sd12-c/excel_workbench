"""数据透视页面：可视化选择行 / 列 / 值 / 聚合方式，一键输出新文件。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget)

from app.core.pivot import (AGGREGATION_CHOICES, build_pivot,
                            list_pivot_sheets, read_pivot_columns)
from app.ui.scheme import scheme_str
from app.ui.widgets.form_helpers import (Card, PathPicker,
                                          default_output_path, labeled_row)

from .base_page import BasePage
from .template_page import _FilePicker


class PivotPage(BasePage):
    PAGE_TITLE = "数据透视"
    PAGE_SUBTITLE = "选好行、列、值和聚合方式，一键生成透视表；不需要会 Excel 数据透视表"
    SCHEME_KEY = "pivot"

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

        data_card = Card("1. 选择数据源")
        self.data_picker = _FilePicker(
            "选择 Excel / CSV 数据源",
            "数据源 (*.xlsx *.xls *.xlsm *.csv);;所有文件 (*.*)")
        data_card.add(labeled_row("数据源文件", self.data_picker))

        self.combo_sheet = QComboBox()
        self.combo_sheet.setMinimumWidth(220)
        data_card.add(labeled_row("工作表", self.combo_sheet))
        data_hint = QLabel(
            "数据源第一行作为列名。透视表会生成一个全新的 xlsx，不会修改原文件。")
        data_hint.setObjectName("HintLabel")
        data_hint.setWordWrap(True)
        data_card.add(data_hint)
        root.addWidget(data_card)

        setting_card = Card("2. 透视设置")
        self.combo_row = QComboBox()
        self.combo_column = QComboBox()
        self.combo_value = QComboBox()
        self.combo_agg = QComboBox()
        for key, label in AGGREGATION_CHOICES:
            self.combo_agg.addItem(label, key)

        setting_card.add(labeled_row("行字段", self.combo_row))
        setting_card.add(labeled_row("列字段", self.combo_column))
        setting_card.add(labeled_row("值字段", self.combo_value))
        setting_card.add(labeled_row("聚合方式", self.combo_agg))

        self.field_label = QLabel("先选择数据源和工作表。")
        self.field_label.setObjectName("HintLabel")
        self.field_label.setWordWrap(True)
        setting_card.add(self.field_label)
        root.addWidget(setting_card)

        output_card = Card("3. 输出")
        self.output_picker = PathPicker("save", "选择输出 xlsx 文件")
        self.output_picker.set_path(default_output_path("透视表.xlsx"))
        output_card.add(labeled_row("输出文件", self.output_picker))
        output_hint = QLabel(
            "同名文件已存在时会自动追加序号，不覆盖原文件。")
        output_hint.setObjectName("HintLabel")
        output_hint.setWordWrap(True)
        output_card.add(output_hint)
        root.addWidget(output_card)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_run = QPushButton("生成透视表")
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

        self.data_picker.changed.connect(self._on_data_changed)
        self.combo_sheet.currentIndexChanged.connect(self._refresh_columns)
        self.busy_changed.connect(self._on_busy)

    def _on_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_run.setText("生成中…" if busy else "生成透视表")

    def _on_data_changed(self, _path: str = "") -> None:
        path = self.data_picker.path()
        self.combo_sheet.blockSignals(True)
        self.combo_sheet.clear()
        if not path:
            self.combo_sheet.blockSignals(False)
            self._clear_fields()
            return
        try:
            sheets = list_pivot_sheets(path)
        except Exception as exc:  # noqa: BLE001
            self.combo_sheet.blockSignals(False)
            self.report_exception(exc, "读取数据源工作表")
            self._clear_fields()
            return
        self.combo_sheet.addItems(sheets)
        self.combo_sheet.blockSignals(False)
        self._refresh_columns()

    def _clear_fields(self) -> None:
        for combo in (self.combo_row, self.combo_column, self.combo_value):
            combo.clear()
        self.field_label.setText("先选择数据源和工作表。")

    def _refresh_columns(self, *_args) -> None:
        path = self.data_picker.path()
        sheet = self.combo_sheet.currentText()
        if not path:
            self._clear_fields()
            return
        try:
            columns = read_pivot_columns(path, sheet)
        except Exception as exc:  # noqa: BLE001
            self.report_exception(exc, "读取数据列")
            self._clear_fields()
            return

        current_row = self.combo_row.currentText()
        current_column = self.combo_column.currentText()
        current_value = self.combo_value.currentText()
        for combo in (self.combo_row, self.combo_column, self.combo_value):
            combo.blockSignals(True)
            combo.clear()

        self.combo_row.addItems(columns)
        self.combo_column.addItem("（不使用）", "")
        for column in columns:
            self.combo_column.addItem(column, column)
        self.combo_value.addItems(columns)

        if current_row in columns:
            self.combo_row.setCurrentText(current_row)
        if current_column:
            index = self.combo_column.findData(current_column)
            if index >= 0:
                self.combo_column.setCurrentIndex(index)
        if current_value in columns:
            self.combo_value.setCurrentText(current_value)
        if not current_value and len(columns) >= 2:
            self.combo_value.setCurrentIndex(1)
        for combo in (self.combo_row, self.combo_column, self.combo_value):
            combo.blockSignals(False)

        self.field_label.setText(
            f"可用字段：{'、'.join(columns)}。列字段可以留空，表示只按行汇总。")

    def _run(self) -> None:
        path = self.data_picker.path()
        if not path:
            self.log_message.emit("请选择数据源文件", "warn")
            return
        row_field = self.combo_row.currentText().strip()
        column_field = self.combo_column.currentData() or ""
        value_field = self.combo_value.currentText().strip()
        output = self.output_picker.path()
        if not row_field or not value_field:
            self.log_message.emit("请选择行字段和值字段", "warn")
            return
        if not output:
            self.log_message.emit("请选择输出文件", "warn")
            return

        aggfunc = self.combo_agg.currentData()
        self.log_message.emit("开始生成透视表", "info")
        self.run_task(
            build_pivot,
            path,
            self.combo_sheet.currentText(),
            row_field,
            column_field,
            value_field,
            aggfunc,
            output,
        )

    def to_scheme(self) -> dict:
        return {
            "data_path": self.data_picker.path(),
            "sheet": self.combo_sheet.currentText(),
            "row": self.combo_row.currentText(),
            "column": self.combo_column.currentData() or "",
            "value": self.combo_value.currentText(),
            "agg": self.combo_agg.currentData(),
            "output": self.output_picker.path(),
        }

    def apply_scheme(self, data: dict) -> None:
        self.data_picker.set_path(scheme_str(data, "data_path", ""))
        sheet = scheme_str(data, "sheet", "")
        if sheet:
            index = self.combo_sheet.findText(sheet)
            if index >= 0:
                self.combo_sheet.setCurrentIndex(index)
        self._refresh_columns()

        row = scheme_str(data, "row", "")
        if row:
            index = self.combo_row.findText(row)
            if index >= 0:
                self.combo_row.setCurrentIndex(index)
        column = scheme_str(data, "column", "")
        index = self.combo_column.findData(column) if column else 0
        if index >= 0:
            self.combo_column.setCurrentIndex(index)
        value = scheme_str(data, "value", "")
        if value:
            index = self.combo_value.findText(value)
            if index >= 0:
                self.combo_value.setCurrentIndex(index)
        agg = scheme_str(data, "agg", "sum")
        index = self.combo_agg.findData(agg)
        if index >= 0:
            self.combo_agg.setCurrentIndex(index)
        self.output_picker.set_path(
            scheme_str(data, "output", self.output_picker.path()))
