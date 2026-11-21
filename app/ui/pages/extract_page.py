"""提取与替换页面。"""
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QRadioButton, QScrollArea,
                             QTabWidget, QVBoxLayout, QWidget)

from app.core.common import split_csv_line
from app.core.extractor import (extract_columns, read_replacement_map,
                                replace_content)
from app.ui.scheme import scheme_bool, scheme_int, scheme_str
from app.ui.widgets.file_list import FileListWidget
from app.ui.widgets.form_helpers import (Card, PathPicker, default_output_path,
                                          labeled_row)

from .base_page import BasePage


class ExtractPage(BasePage):
    PAGE_TITLE = "提取与替换"
    PAGE_SUBTITLE = "批量提取指定列；支持单条替换与导入对照表批量替换（可选正则）"
    SCHEME_KEY = "extract"

    def build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        files_card = Card("源文件")
        self.file_list = FileListWidget("拖拽 Excel 文件 / 文件夹到此处")
        files_card.add(self.file_list, 1)
        root.addWidget(files_card, 1)

        output_card = Card()
        self.output_picker = PathPicker("dir", "选择输出目录")
        self.output_picker.set_path(default_output_path("输出结果"))
        output_card.add(labeled_row("输出目录", self.output_picker))
        root.addWidget(output_card)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_extract_tab(), "提取指定列")
        self.tabs.addTab(self._build_replace_tab(), "批量替换内容")
        root.addWidget(self.tabs, 1)

        self.busy_changed.connect(self._on_busy)

    # ------------------------------------------------------------ 子页
    def _build_extract_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        card = Card()
        self.edit_columns = QLineEdit()
        self.edit_columns.setPlaceholderText("例如：姓名, 手机号, 部门（中英文逗号均可）")
        card.add(labeled_row("提取列名", self.edit_columns))

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_extract = QPushButton("开始提取")
        self.btn_extract.setObjectName("PrimaryButton")
        self.btn_extract.setCursor(Qt.PointingHandCursor)
        self.btn_extract.setMinimumWidth(140)
        self.btn_extract.clicked.connect(self._run_extract)
        row.addWidget(self.btn_extract)
        card.add_layout(row)

        layout.addWidget(card)
        layout.addStretch(1)
        return tab

    def _build_replace_tab(self) -> QWidget:
        tab = QWidget()
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QWidget()
        content.setObjectName("ScrollBody")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        card = Card()
        card.body.setSpacing(8)
        card.body.setContentsMargins(16, 12, 16, 12)

        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(24)
        self.radio_single = QRadioButton("单条替换")
        self.radio_single.setChecked(True)
        self.radio_mapping = QRadioButton("导入对照表批量替换")
        mode_layout.addWidget(self.radio_single)
        mode_layout.addWidget(self.radio_mapping)
        mode_layout.addStretch(1)
        card.add(labeled_row("替换方式", mode_row))

        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("需要查找的内容")
        self.search_row = labeled_row("查找内容", self.edit_search)
        card.add(self.search_row)

        self.edit_replace = QLineEdit()
        self.edit_replace.setPlaceholderText("替换为（留空表示删除）")
        self.replace_row = labeled_row("替换为", self.edit_replace)
        card.add(self.replace_row)

        self.mapping_picker = PathPicker(
            "open", "选择替换对照表（第一列查找内容，第二列替换为）")
        self.mapping_row = labeled_row("对照表文件", self.mapping_picker)
        card.add(self.mapping_row)

        self.mapping_hint = QLabel(
            "对照表格式：第一列「查找内容」，第二列「替换为」（读取第一张工作表）；"
            "首行可为表头；规则按行顺序执行，替换为留空表示删除")
        self.mapping_hint.setObjectName("HintLabel")
        self.mapping_hint.setWordWrap(True)
        card.add(self.mapping_hint)

        self.edit_scope = QLineEdit()
        self.edit_scope.setPlaceholderText("留空表示对所有列生效（多个列名用逗号分隔）")
        card.add(labeled_row("作用列", self.edit_scope))

        option_row = QHBoxLayout()
        option_row.setSpacing(28)
        self.cb_regex = QCheckBox("使用正则表达式（高级）")
        self.cb_regex.setChecked(False)
        self.cb_regex.setToolTip(
            "默认关闭。开启后查找内容按正则表达式解释，替换内容支持 \\1 等分组引用；"
            "不确定时请勿勾选。")
        self.cb_case = QCheckBox("区分大小写")
        self.cb_case.setChecked(True)
        option_row.addWidget(self.cb_regex)
        option_row.addWidget(self.cb_case)
        option_row.addStretch(1)
        card.add_layout(option_row)

        self.regex_hint = QLabel(
            "⚠ 正则模式已开启：特殊字符会按正则表达式解释，可能导致意外替换，"
            "请确认规则无误。")
        self.regex_hint.setObjectName("HintLabel")
        self.regex_hint.setWordWrap(True)
        self.regex_hint.setStyleSheet("color:#d4380d;")
        self.regex_hint.setVisible(False)
        card.add(self.regex_hint)

        layout.addWidget(card)
        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.btn_replace = QPushButton("开始替换")
        self.btn_replace.setObjectName("PrimaryButton")
        self.btn_replace.setCursor(Qt.PointingHandCursor)
        self.btn_replace.setMinimumWidth(140)
        self.btn_replace.clicked.connect(self._run_replace)
        button_row.addWidget(self.btn_replace)
        outer.addLayout(button_row)

        self.radio_mapping.toggled.connect(self._update_replace_mode)
        self.cb_regex.toggled.connect(self._on_regex_toggled)
        self._update_replace_mode()
        return tab

    # ------------------------------------------------------------ 回调
    def _on_busy(self, busy: bool) -> None:
        self.btn_extract.setEnabled(not busy)
        self.btn_replace.setEnabled(not busy)
        self.btn_extract.setText("提取中…" if busy else "开始提取")
        self.btn_replace.setText("替换中…" if busy else "开始替换")

    def _update_replace_mode(self, *_args) -> None:
        mapping = self.radio_mapping.isChecked()
        self.search_row.setEnabled(not mapping)
        self.replace_row.setEnabled(not mapping)
        self.mapping_row.setEnabled(mapping)
        self.mapping_hint.setVisible(mapping)

    def _on_regex_toggled(self, checked: bool) -> None:
        self.regex_hint.setVisible(checked)
        self.edit_search.setPlaceholderText(
            "正则表达式（例如：\\d{11}）" if checked else "需要查找的内容")

    def to_scheme(self) -> dict:
        return {
            "active_tab": self.tabs.currentIndex(),
            "extract_columns": self.edit_columns.text(),
            "replace_mode": ("mapping" if self.radio_mapping.isChecked()
                             else "single"),
            "search": self.edit_search.text(),
            "replace": self.edit_replace.text(),
            "scope": self.edit_scope.text(),
            "regex": self.cb_regex.isChecked(),
            "case_sensitive": self.cb_case.isChecked(),
            "mapping_file": self.mapping_picker.path(),
            "output": self.output_picker.path(),
        }

    def apply_scheme(self, data: dict) -> None:
        tab_index = scheme_int(data, "active_tab", 0)
        if 0 <= tab_index < self.tabs.count():
            self.tabs.setCurrentIndex(tab_index)

        self.edit_columns.setText(scheme_str(data, "extract_columns", ""))

        mapping = scheme_str(data, "replace_mode", "single") == "mapping"
        self.radio_mapping.setChecked(mapping)
        self.radio_single.setChecked(not mapping)
        self.edit_search.setText(scheme_str(data, "search", ""))
        self.edit_replace.setText(scheme_str(data, "replace", ""))
        self.edit_scope.setText(scheme_str(data, "scope", ""))
        self.cb_regex.setChecked(scheme_bool(data, "regex", False))
        self.cb_case.setChecked(scheme_bool(data, "case_sensitive", True))
        self.mapping_picker.set_path(
            scheme_str(data, "mapping_file", self.mapping_picker.path()))
        self.output_picker.set_path(
            scheme_str(data, "output", self.output_picker.path()))
        self._update_replace_mode()

    def _guard(self):
        files = self.file_list.files()
        if not files:
            self.log_message.emit("请先添加需要处理的文件", "warn")
            return None, None
        output = self.output_picker.path()
        if not output:
            self.log_message.emit("请选择输出目录", "warn")
            return None, None
        return files, output

    def _run_extract(self) -> None:
        files, output = self._guard()
        if not files:
            return
        columns = split_csv_line(self.edit_columns.text())
        if not columns:
            self.log_message.emit("请填写需要提取的列名", "warn")
            return
        self.run_task(extract_columns, files, columns, output)

    def _run_replace(self) -> None:
        files, output = self._guard()
        if not files:
            return

        columns = split_csv_line(self.edit_scope.text()) or None
        regex = self.cb_regex.isChecked()

        if self.radio_mapping.isChecked():
            mapping_path = self.mapping_picker.path()
            if not mapping_path:
                self.log_message.emit("请选择替换对照表文件", "warn")
                return
            try:
                rules = read_replacement_map(mapping_path)
            except Exception as exc:  # noqa: BLE001
                self.report_exception(exc, "读取替换对照表")
                return

            if regex:
                for index, (pattern, replacement) in enumerate(rules, start=1):
                    try:
                        compiled = re.compile(pattern)
                        compiled.sub(replacement, "")
                    except re.error as exc:
                        self.log_message.emit(
                            f"✗ 对照表第 {index} 条规则的正则表达式无效：{exc}",
                            "error")
                        return

            self.run_task(
                replace_content, files, "", "", output,
                columns=columns,
                regex=regex,
                case_sensitive=self.cb_case.isChecked(),
                replacement_map=rules,
            )
            return

        search = self.edit_search.text()
        if not search:
            self.log_message.emit("请填写需要查找的内容", "warn")
            return
        if regex:
            try:
                compiled = re.compile(search)
                compiled.sub(self.edit_replace.text(), "")
            except re.error as exc:
                self.log_message.emit(f"✗ 正则表达式无效：{exc}", "error")
                return

        self.run_task(
            replace_content, files, search, self.edit_replace.text(), output,
            columns=columns,
            regex=regex,
            case_sensitive=self.cb_case.isChecked(),
        )
