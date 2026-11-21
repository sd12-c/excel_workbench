"""合并工作表页面。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QRadioButton,
                             QScrollArea, QVBoxLayout, QWidget)

from app.core.merger import merge_files
from app.ui.scheme import scheme_bool, scheme_str
from app.ui.widgets.file_list import FileListWidget
from app.ui.widgets.form_helpers import Card, PathPicker, default_output_path, labeled_row
from app.ui.widgets.output_guard import resolve_output_file

from .base_page import BasePage


class MergePage(BasePage):
    PAGE_TITLE = "合并工作表"
    PAGE_SUBTITLE = "将多个 Excel 文件（支持多工作表）合并为一张总表，可按表头对齐或仅保留共有列"
    SCHEME_KEY = "merge"

    def build_ui(self) -> None:
        # 选项较多，用滚动区域保证小窗口下也能完整操作
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

        option_card = Card("合并选项")
        option_card.body.setSpacing(8)
        option_card.body.setContentsMargins(16, 12, 16, 12)
        
        # 基础选项
        self.cb_all_sheets = QCheckBox("合并每个文件中的所有工作表")
        self.cb_all_sheets.setChecked(True)
        self.cb_source = QCheckBox("添加来源列（文件 / 工作表）")
        self.cb_source.setChecked(True)
        self.cb_source.setToolTip("列名可在下方「来源列名称」中自定义")
        self.cb_ignore_empty = QCheckBox("忽略空工作表 / 空数据")
        self.cb_ignore_empty.setChecked(True)
        self.cb_auto_rename = QCheckBox("目标文件已存在时自动重命名（推荐）")
        self.cb_auto_rename.setChecked(True)
        self.cb_auto_rename.setToolTip(
            "避免覆盖同名文件；目标文件被 Excel / WPS 占用时也能自动换名保存")

        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(10)
        grid.addWidget(self.cb_all_sheets, 0, 0)
        grid.addWidget(self.cb_source, 0, 1)
        grid.addWidget(self.cb_ignore_empty, 1, 0)
        grid.addWidget(self.cb_auto_rename, 1, 1)
        option_card.add_layout(grid)

        align_row = QWidget()
        align_layout = QHBoxLayout(align_row)
        align_layout.setContentsMargins(0, 0, 0, 0)
        align_layout.setSpacing(20)
        self.radio_union = QRadioButton("按表头合并（缺列填空）")
        self.radio_union.setChecked(True)
        self.radio_union.setToolTip("保留所有出现过的列；某个文件缺少的列自动留空")
        self.radio_intersection = QRadioButton("只保留所有文件共有的列（交集）")
        self.radio_intersection.setToolTip("各文件表头不一致时，只保留每个文件都包含的列")
        align_layout.addWidget(self.radio_union)
        align_layout.addWidget(self.radio_intersection)
        align_layout.addStretch(1)
        option_card.add(labeled_row("列对齐策略", align_row))

        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(8)
        self.label_source_column = QLabel("文件列名")
        self.label_source_column.setObjectName("FieldLabel")
        self.edit_source_column = QLineEdit("来源文件")
        self.edit_source_column.setPlaceholderText("来源文件列名")
        self.edit_source_column.setToolTip("留空则使用默认名称「来源文件」")
        self.label_sheet_column = QLabel("工作表列名")
        self.label_sheet_column.setObjectName("FieldLabel")
        self.edit_sheet_column = QLineEdit("来源工作表")
        self.edit_sheet_column.setPlaceholderText("来源工作表列名")
        self.edit_sheet_column.setToolTip(
            "留空则使用默认名称「来源工作表」；仅在勾选「合并每个文件中的所有工作表」时生效")
        source_layout.addWidget(self.label_source_column)
        source_layout.addWidget(self.edit_source_column, 1)
        source_layout.addWidget(self.label_sheet_column)
        source_layout.addWidget(self.edit_sheet_column, 1)
        option_card.add(labeled_row("来源列名称", source_row))

        self.cb_source.toggled.connect(self._update_source_fields)
        self.cb_all_sheets.toggled.connect(self._update_source_fields)
        self._update_source_fields()

        self.edit_sort_columns = QLineEdit()
        self.edit_sort_columns.setPlaceholderText("不填则保持原顺序（例如：日期, 部门）")
        option_card.add(labeled_row("排序依据列", self.edit_sort_columns))

        sort_row = QWidget()
        sort_layout = QHBoxLayout(sort_row)
        sort_layout.setContentsMargins(0, 0, 0, 0)
        sort_layout.setSpacing(24)
        
        self.radio_asc = QRadioButton("升序 (A-Z, 1-9, 最早-最晚)")
        self.radio_asc.setChecked(True)
        self.radio_desc = QRadioButton("降序 (Z-A, 9-1, 最晚-最早)")
        sort_layout.addWidget(self.radio_asc)
        sort_layout.addWidget(self.radio_desc)
        sort_layout.addStretch(1)
        option_card.add(labeled_row("排序方式", sort_row))

        # 输出文件
        self.output_picker = PathPicker("save", "选择合并结果的保存位置（.xlsx）")
        self.output_picker.set_path(default_output_path("合并结果.xlsx"))
        option_card.add(labeled_row("输出文件", self.output_picker))
        root.addWidget(option_card)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_run = QPushButton("开始合并")
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

        self.busy_changed.connect(self._on_busy)

    # ------------------------------------------------------------ 内部
    def _on_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_run.setText("合并中…" if busy else "开始合并")

    def _update_source_fields(self, *_args) -> None:
        add_source = self.cb_source.isChecked()
        self.label_source_column.setEnabled(add_source)
        self.edit_source_column.setEnabled(add_source)
        sheet_enabled = add_source and self.cb_all_sheets.isChecked()
        self.label_sheet_column.setEnabled(sheet_enabled)
        self.edit_sheet_column.setEnabled(sheet_enabled)

    def to_scheme(self) -> dict:
        return {
            "all_sheets": self.cb_all_sheets.isChecked(),
            "add_source": self.cb_source.isChecked(),
            "ignore_empty": self.cb_ignore_empty.isChecked(),
            "auto_rename": self.cb_auto_rename.isChecked(),
            "alignment": ("intersection" if self.radio_intersection.isChecked()
                          else "union"),
            "source_column": self.edit_source_column.text(),
            "sheet_column": self.edit_sheet_column.text(),
            "sort_columns": self.edit_sort_columns.text(),
            "sort_ascending": self.radio_asc.isChecked(),
            "output": self.output_picker.path(),
        }

    def apply_scheme(self, data: dict) -> None:
        self.cb_all_sheets.setChecked(scheme_bool(data, "all_sheets", True))
        self.cb_source.setChecked(scheme_bool(data, "add_source", True))
        self.cb_ignore_empty.setChecked(scheme_bool(data, "ignore_empty", True))
        self.cb_auto_rename.setChecked(scheme_bool(data, "auto_rename", True))

        intersection = scheme_str(data, "alignment", "union") == "intersection"
        self.radio_intersection.setChecked(intersection)
        self.radio_union.setChecked(not intersection)

        self.edit_source_column.setText(
            scheme_str(data, "source_column", "来源文件"))
        self.edit_sheet_column.setText(
            scheme_str(data, "sheet_column", "来源工作表"))
        self.edit_sort_columns.setText(scheme_str(data, "sort_columns", ""))

        ascending = scheme_bool(data, "sort_ascending", True)
        self.radio_asc.setChecked(ascending)
        self.radio_desc.setChecked(not ascending)

        self.output_picker.set_path(
            scheme_str(data, "output", self.output_picker.path()))
        self._update_source_fields()

    def _run(self) -> None:
        if self.is_busy:
            self.log_message.emit("已有任务正在执行，请稍候……", "warn")
            return
        files = self.file_list.files()
        if not files:
            self.log_message.emit("请先添加需要合并的 Excel 文件", "warn")
            return
        output = self.output_picker.path()
        if not output:
            self.log_message.emit("请选择输出文件位置", "warn")
            return
        if not output.lower().endswith(".xlsx"):
            output += ".xlsx"

        add_source = self.cb_source.isChecked()
        all_sheets = self.cb_all_sheets.isChecked()
        source_column = self.edit_source_column.text().strip() or "来源文件"
        sheet_column = self.edit_sheet_column.text().strip() or "来源工作表"
        if add_source and all_sheets and source_column == sheet_column:
            self.log_message.emit(
                "来源文件列名与来源工作表列名不能相同，请修改后再试", "warn")
            return
        alignment = ("intersection"
                     if self.radio_intersection.isChecked() else "union")

        output = resolve_output_file(
            self, output,
            auto_rename=self.cb_auto_rename.isChecked(),
            log=self.log_message.emit,
        )
        if not output:
            return

        self.log_message.emit(
            f"开始合并 {len(files)} 个文件……", "info")

        self.run_task(
            merge_files, files, output,
            all_sheets=all_sheets,
            add_source=add_source,
            source_column=source_column,
            sheet_column=sheet_column,
            alignment=alignment,
            ignore_empty_sheets=self.cb_ignore_empty.isChecked(),
            sort_columns=self.edit_sort_columns.text(),
            sort_ascending=self.radio_asc.isChecked()
        )

    def on_task_done(self, result) -> None:
        if not isinstance(result, dict):
            return
        strategy = ("仅保留共有列"
                    if result.get("alignment") == "intersection"
                    else "按表头合并")
        self.log_message.emit(
            f"合并结果：{result.get('rows', 0)} 行 × {result.get('cols', 0)} 列"
            f"（{strategy}），失败 {result.get('failed', 0)} 个文件", "info")