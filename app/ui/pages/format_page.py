"""批量格式化页面。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox,
                             QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QScrollArea, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from app.core.clean_rules import (COLUMN_RULES, ColumnBinding,
                                  column_bindings_to_dict, load_clean_plan,
                                  normalize_column_bindings, save_clean_plan)
from app.core.common import split_csv_line
from app.core.formatter import format_files
from app.core.preview import read_preview
from app.ui.scheme import scheme_bool, scheme_str
from app.ui.widgets.file_list import FileListWidget
from app.ui.widgets.form_helpers import (Card, PathPicker, default_output_path,
                                          labeled_row)

from .base_page import BasePage


class FormatPage(BasePage):
    PAGE_TITLE = "批量格式化"
    PAGE_SUBTITLE = "原子清洗：全局规则 + 单列绑定（手机号/金额/日期），按规则写出数字格式与对齐"
    SCHEME_KEY = "format"

    def build_ui(self) -> None:
        self._bindings = []
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

        option_card = Card("清洗规则")
        option_card.body.setSpacing(8)
        option_card.body.setContentsMargins(16, 12, 16, 12)

        global_title = QLabel("全局规则（整表，先执行）")
        global_title.setObjectName("FieldLabel")
        option_card.add(global_title)

        self.cb_empty_rows = QCheckBox("清除完全为空的行")
        self.cb_empty_rows.setChecked(True)
        self.cb_empty_cols = QCheckBox("清除完全为空的列")
        self.cb_strip = QCheckBox("去除文本首尾空格")
        self.cb_strip.setChecked(True)
        self.cb_hyperlinks = QCheckBox("清除超链接")
        self.cb_hyperlinks.setChecked(True)
        self.cb_hyperlinks.setToolTip("输出为纯数据，不保留单元格超链接")
        self.cb_comments = QCheckBox("清除批注")
        self.cb_comments.setChecked(True)
        self.cb_comments.setToolTip("输出为纯数据，不保留单元格批注")
        self.cb_numbers = QCheckBox("数字统一格式（去千分位 / 文本转数值）")
        self.cb_numbers.setChecked(True)
        self.cb_numbers.setToolTip(
            "把「1,234.5」「￥1,200」等文本转为数值；"
            "编号、手机号、超长数字保留原样")

        grid = QGridLayout()
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(10)
        grid.addWidget(self.cb_empty_rows, 0, 0)
        grid.addWidget(self.cb_empty_cols, 0, 1)
        grid.addWidget(self.cb_strip, 1, 0)
        grid.addWidget(self.cb_hyperlinks, 2, 0)
        grid.addWidget(self.cb_comments, 2, 1)
        grid.addWidget(self.cb_numbers, 3, 0, 1, 2)
        option_card.add_layout(grid)

        self.cb_duplicates = QCheckBox("删除重复行")
        option_card.add(self.cb_duplicates)

        self.edit_dedup = QLineEdit()
        self.edit_dedup.setPlaceholderText("留空表示按全部列判断（多个列名用逗号分隔）")
        option_card.add(labeled_row("去重依据列", self.edit_dedup))

        self.cb_dates = QCheckBox("统一日期格式")
        self.cb_dates.setChecked(True)
        option_card.add(self.cb_dates)

        self.edit_dates = QLineEdit()
        self.edit_dates.setPlaceholderText("留空表示自动识别（多个列名用逗号分隔）")
        option_card.add(labeled_row("日期列", self.edit_dates))

        self.edit_date_format = QLineEdit("%Y-%m-%d")
        option_card.add(labeled_row("目标格式", self.edit_date_format))

        self.cb_chinese_dates = QCheckBox(
            "自动识别多种中文日期（2026年11月21日 / 11月21日）")
        self.cb_chinese_dates.setChecked(True)
        self.cb_chinese_dates.setToolTip(
            "支持 -、/、年月日等写法；缺少年份时按当前年份补全，"
            "无法识别的行会在日志中标记并保留原值")
        option_card.add(self.cb_chinese_dates)

        bind_title = QLabel("单列绑定规则（全局规则之后执行）")
        bind_title.setObjectName("FieldLabel")
        option_card.add(bind_title)
        bind_hint = QLabel(
            "先选列，再选原子规则；日期规则使用上方“目标格式”。"
            "同一列可以按顺序绑定多条规则。")
        bind_hint.setObjectName("HintLabel")
        bind_hint.setWordWrap(True)
        option_card.add(bind_hint)

        self.combo_bind_column = QComboBox()
        self.combo_bind_column.setEditable(True)
        self.combo_bind_column.setMinimumWidth(150)
        self.combo_bind_column.lineEdit().setPlaceholderText("选择或输入列名")
        self.combo_bind_rule = QComboBox()
        self.combo_bind_rule.setMinimumWidth(280)
        for rule in COLUMN_RULES.values():
            self.combo_bind_rule.addItem(
                f"{rule.label} · {rule.description}", rule.key)

        self.btn_bind_add = QPushButton("添加绑定")
        self.btn_bind_remove = QPushButton("删除选中")
        self.btn_bind_refresh = QPushButton("刷新列名")
        for button in (self.btn_bind_add, self.btn_bind_remove,
                       self.btn_bind_refresh):
            button.setObjectName("GhostButton")
            button.setCursor(Qt.PointingHandCursor)

        bind_bar = QHBoxLayout()
        bind_bar.setSpacing(8)
        bind_bar.addWidget(self.combo_bind_column, 1)
        bind_bar.addWidget(self.combo_bind_rule, 2)
        bind_bar.addWidget(self.btn_bind_add)
        bind_bar.addWidget(self.btn_bind_remove)
        bind_bar.addWidget(self.btn_bind_refresh)
        option_card.add_layout(bind_bar)

        self.table_bindings = QTableWidget(0, 3)
        self.table_bindings.setHorizontalHeaderLabels(
            ["列名", "原子规则", "写入格式"])
        self.table_bindings.verticalHeader().setVisible(False)
        self.table_bindings.setSelectionBehavior(
            QAbstractItemView.SelectRows)
        self.table_bindings.setSelectionMode(
            QAbstractItemView.ExtendedSelection)
        self.table_bindings.setEditTriggers(
            QAbstractItemView.NoEditTriggers)
        self.table_bindings.setMinimumHeight(110)
        self.table_bindings.setMaximumHeight(180)
        header = self.table_bindings.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        option_card.add(self.table_bindings)

        rule_bar = QHBoxLayout()
        rule_bar.addStretch(1)
        self.btn_rules_save = QPushButton("保存规则…")
        self.btn_rules_load = QPushButton("加载规则…")
        for button in (self.btn_rules_save, self.btn_rules_load):
            button.setObjectName("GhostButton")
            button.setCursor(Qt.PointingHandCursor)
            rule_bar.addWidget(button)
        option_card.add_layout(rule_bar)

        self.output_picker = PathPicker("dir", "选择清洗结果的输出目录")
        self.output_picker.set_path(default_output_path("格式化输出"))
        option_card.add(labeled_row("输出目录", self.output_picker))
        root.addWidget(option_card)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_run = QPushButton("开始处理")
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

        self.cb_dates.toggled.connect(self._update_date_fields)
        self._update_date_fields()
        self.btn_bind_add.clicked.connect(self._add_binding)
        self.btn_bind_remove.clicked.connect(self._remove_bindings)
        self.btn_bind_refresh.clicked.connect(self._refresh_bind_columns)
        self.btn_rules_save.clicked.connect(self._save_rules)
        self.btn_rules_load.clicked.connect(self._load_rules)
        self.file_list.changed.connect(self._on_files_changed)
        self._refresh_binding_table()
        self.busy_changed.connect(self._on_busy)

    # ------------------------------------------------------------ 内部
    def _on_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_run.setText("处理中…" if busy else "开始处理")

    def _update_date_fields(self, *_args) -> None:
        global_dates = self.cb_dates.isChecked()
        has_date_binding = any(item.rule == "date"
                               for item in self._bindings)
        self.edit_dates.setEnabled(global_dates)
        self.edit_date_format.setEnabled(global_dates or has_date_binding)
        self.cb_chinese_dates.setEnabled(global_dates or has_date_binding)

    # ------------------------------------------------------------ 规则编辑
    def _global_rule_widgets(self):
        return [
            ("remove_empty_rows", self.cb_empty_rows),
            ("remove_empty_cols", self.cb_empty_cols),
            ("strip_text", self.cb_strip),
            ("clear_hyperlinks", self.cb_hyperlinks),
            ("clear_comments", self.cb_comments),
            ("normalize_numbers", self.cb_numbers),
            ("drop_duplicates", self.cb_duplicates),
            ("normalize_dates", self.cb_dates),
        ]

    def _selected_global_rules(self):
        return [key for key, widget in self._global_rule_widgets()
                if widget.isChecked()]

    def _apply_global_rules(self, keys) -> None:
        selected = set(keys or [])
        for key, widget in self._global_rule_widgets():
            widget.setChecked(key in selected)
        self._update_date_fields()

    def _on_files_changed(self, _files) -> None:
        # 文件变化后如果还没有列名，自动尝试读取一次表头。
        if self.combo_bind_column.count() == 0:
            self._refresh_bind_columns()

    def _refresh_bind_columns(self) -> None:
        columns = []
        for path in self.file_list.files()[:10]:
            try:
                preview = read_preview(path, rows=1)
            except Exception:  # noqa: BLE001
                continue
            for column in preview.columns:
                if column not in columns:
                    columns.append(column)

        current = self.combo_bind_column.currentText().strip()
        self.combo_bind_column.blockSignals(True)
        self.combo_bind_column.clear()
        self.combo_bind_column.addItems(columns)
        if current:
            self.combo_bind_column.setEditText(current)
        elif columns:
            self.combo_bind_column.setCurrentIndex(0)
        self.combo_bind_column.blockSignals(False)
        if not columns:
            self.log_message.emit(
                "没有读取到列名，请先添加文件，或直接手动输入列名。", "warn")

    def _add_binding(self) -> None:
        column = self.combo_bind_column.currentText().strip()
        rule_key = self.combo_bind_rule.currentData()
        rule = COLUMN_RULES.get(rule_key)
        if not column:
            self.log_message.emit("请先选择或输入要绑定的列名", "warn")
            return
        if rule is None:
            self.log_message.emit("请选择有效的原子规则", "warn")
            return
        if any(item.column == column and item.rule == rule_key
               for item in self._bindings):
            self.log_message.emit(
                f"列“{column}”已经绑定了“{rule.label}”，无需重复添加", "warn")
            return
        self._bindings.append(ColumnBinding(column=column, rule=rule_key))
        self._refresh_binding_table()
        self._update_date_fields()
        self.log_message.emit(
            f"已添加绑定：{column} → {rule.label}", "info")

    def _remove_bindings(self) -> None:
        selected = self.table_bindings.selectionModel()
        rows = sorted({index.row() for index in selected.selectedRows()},
                      reverse=True)
        if not rows:
            self.log_message.emit("请先在绑定清单中选中要删除的行", "warn")
            return
        for row in rows:
            if 0 <= row < len(self._bindings):
                del self._bindings[row]
        self._refresh_binding_table()
        self._update_date_fields()

    def _refresh_binding_table(self) -> None:
        self.table_bindings.setRowCount(len(self._bindings))
        for row, binding in enumerate(self._bindings):
            rule = COLUMN_RULES.get(binding.rule)
            rule_label = rule.label if rule else binding.rule
            format_label = "—"
            if rule:
                format_label = f"{rule.number_format or '—'} · {rule.alignment or '—'}"
            for column, text in enumerate(
                    (binding.column, rule_label, format_label)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table_bindings.setItem(row, column, item)
        self._update_date_fields()

    def _clean_options(self) -> dict:
        return {
            "dedup_columns": self.edit_dedup.text(),
            "date_columns": self.edit_dates.text(),
            "date_format": self.edit_date_format.text(),
            "recognize_chinese_dates": self.cb_chinese_dates.isChecked(),
        }

    def _apply_clean_options(self, options: dict) -> None:
        if not isinstance(options, dict):
            return
        self.edit_dedup.setText(str(options.get("dedup_columns", "")))
        self.edit_dates.setText(str(options.get("date_columns", "")))
        self.edit_date_format.setText(
            str(options.get("date_format", "%Y-%m-%d")))
        if "recognize_chinese_dates" in options:
            self.cb_chinese_dates.setChecked(
                bool(options.get("recognize_chinese_dates")))

    def _save_rules(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "保存清洗规则", "清洗规则.json", "JSON 文件 (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_clean_plan(path, self._selected_global_rules(),
                            self._bindings, self._clean_options())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        self.log_message.emit(f"已保存清洗规则：{path}", "success")

    def _load_rules(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载清洗规则", "", "JSON 文件 (*.json)")
        if not path:
            return
        try:
            data = load_clean_plan(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "加载失败", str(exc))
            return
        self._apply_global_rules(data.get("global_rules", []))
        self._bindings = normalize_column_bindings(
            data.get("column_bindings", []))
        self._refresh_binding_table()
        self._apply_clean_options(data.get("options", {}))
        self.log_message.emit(f"已加载清洗规则：{path}", "success")

    def to_scheme(self) -> dict:
        return {
            "empty_rows": self.cb_empty_rows.isChecked(),
            "empty_cols": self.cb_empty_cols.isChecked(),
            "strip_text": self.cb_strip.isChecked(),
            "hyperlinks": self.cb_hyperlinks.isChecked(),
            "comments": self.cb_comments.isChecked(),
            "numbers": self.cb_numbers.isChecked(),
            "duplicates": self.cb_duplicates.isChecked(),
            "dedup_columns": self.edit_dedup.text(),
            "dates": self.cb_dates.isChecked(),
            "date_columns": self.edit_dates.text(),
            "date_format": self.edit_date_format.text(),
            "chinese_dates": self.cb_chinese_dates.isChecked(),
            "global_rules": self._selected_global_rules(),
            "column_bindings": column_bindings_to_dict(self._bindings),
            "output": self.output_picker.path(),
        }

    def apply_scheme(self, data: dict) -> None:
        global_rules = data.get("global_rules")
        if isinstance(global_rules, list):
            self._apply_global_rules(global_rules)
        else:
            self.cb_empty_rows.setChecked(
                scheme_bool(data, "empty_rows", True))
            self.cb_empty_cols.setChecked(
                scheme_bool(data, "empty_cols", False))
            self.cb_strip.setChecked(scheme_bool(data, "strip_text", True))
            self.cb_hyperlinks.setChecked(
                scheme_bool(data, "hyperlinks", True))
            self.cb_comments.setChecked(scheme_bool(data, "comments", True))
            self.cb_numbers.setChecked(scheme_bool(data, "numbers", True))
            self.cb_duplicates.setChecked(
                scheme_bool(data, "duplicates", False))
            self.cb_dates.setChecked(scheme_bool(data, "dates", True))
        self.edit_dedup.setText(scheme_str(data, "dedup_columns", ""))
        self.edit_dates.setText(scheme_str(data, "date_columns", ""))
        self.edit_date_format.setText(
            scheme_str(data, "date_format", "%Y-%m-%d"))
        self.cb_chinese_dates.setChecked(
            scheme_bool(data, "chinese_dates", True))
        self._bindings = normalize_column_bindings(
            data.get("column_bindings", []))
        self._refresh_binding_table()
        self.output_picker.set_path(
            scheme_str(data, "output", self.output_picker.path()))
        self._update_date_fields()

    def _run(self) -> None:
        files = self.file_list.files()
        if not files:
            self.log_message.emit("请先添加需要处理的文件", "warn")
            return
        output = self.output_picker.path()
        if not output:
            self.log_message.emit("请选择输出目录", "warn")
            return

        date_format = self.edit_date_format.text().strip() or "%Y-%m-%d"
        self.run_task(
            format_files, files, output,
            remove_empty_rows=self.cb_empty_rows.isChecked(),
            remove_empty_cols=self.cb_empty_cols.isChecked(),
            strip_text=self.cb_strip.isChecked(),
            clear_hyperlinks=self.cb_hyperlinks.isChecked(),
            clear_comments=self.cb_comments.isChecked(),
            normalize_numbers=self.cb_numbers.isChecked(),
            drop_duplicates=self.cb_duplicates.isChecked(),
            dedup_columns=split_csv_line(self.edit_dedup.text()),
            normalize_date=self.cb_dates.isChecked(),
            recognize_chinese_dates=self.cb_chinese_dates.isChecked(),
            date_columns=split_csv_line(self.edit_dates.text()),
            date_format=date_format,
            global_rules=self._selected_global_rules(),
            column_bindings=self._bindings,
        )