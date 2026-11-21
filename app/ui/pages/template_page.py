"""模板填充页面：数据源 + xlsx 模板，按行批量生成独立报表。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QFileDialog, QFrame, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from app.core.common import normalize_path
from app.core.template_filler import (fill_template_reports, read_data_columns,
                                      scan_template_markers)
from app.ui.scheme import scheme_bool, scheme_str
from app.ui.widgets.form_helpers import (Card, PathPicker,
                                          default_output_path, labeled_row)

from .base_page import BasePage


class _FilePicker(QWidget):
    """单文件选择控件：文本框 + 浏览按钮 + 文件类型过滤。"""

    changed = pyqtSignal(str)

    def __init__(self, placeholder: str, file_filter: str, parent=None):
        super().__init__(parent)
        self._filter = file_filter
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.button = QPushButton("浏览")
        self.button.setObjectName("GhostButton")
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self._browse)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.button)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", self.edit.text(), self._filter)
        if path:
            self.set_path(path)

    def path(self) -> str:
        return normalize_path(self.edit.text())

    def set_path(self, path: str) -> None:
        self.edit.setText(normalize_path(path))
        self.changed.emit(self.path())


class TemplatePage(BasePage):
    PAGE_TITLE = "模板填充"
    PAGE_SUBTITLE = "一份数据源 + 一份 Excel 模板，按行批量生成独立报表"
    SCHEME_KEY = "template"

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

        data_card = Card("1. 数据源")
        self.data_picker = _FilePicker(
            "选择 Excel 数据源（.xlsx / .xls / .xlsm / .csv）",
            "数据源 (*.xlsx *.xls *.xlsm *.csv);;所有文件 (*.*)")
        data_card.add(labeled_row("数据源文件", self.data_picker))
        data_hint = QLabel(
            "使用数据源的第一张工作表；第一行作为列名，每一行生成一份报表。"
            "编号、手机号等文本列会尽量保留原样。")
        data_hint.setObjectName("HintLabel")
        data_hint.setWordWrap(True)
        data_card.add(data_hint)
        root.addWidget(data_card)

        template_card = Card("2. Excel 模板")
        self.template_picker = _FilePicker(
            "选择 .xlsx 模板文件",
            "Excel 模板 (*.xlsx);;所有文件 (*.*)")
        template_card.add(labeled_row("模板文件", self.template_picker))
        template_hint = QLabel(
            "在模板单元格里写 {{姓名}}、{{金额}}、{{日期}} 这样的标记；"
            "程序会复制模板，并按数据行替换。一个单元格只有一个标记时，"
            "金额/日期会按原数据类型写入。")
        template_hint.setObjectName("HintLabel")
        template_hint.setWordWrap(True)
        template_card.add(template_hint)

        scan_row = QHBoxLayout()
        scan_row.addStretch(1)
        self.btn_scan = QPushButton("检测模板标记")
        self.btn_scan.setObjectName("GhostButton")
        self.btn_scan.setCursor(Qt.PointingHandCursor)
        scan_row.addWidget(self.btn_scan)
        template_card.add_layout(scan_row)

        self.marker_label = QLabel("尚未检测模板标记。")
        self.marker_label.setObjectName("HintLabel")
        self.marker_label.setWordWrap(True)
        template_card.add(self.marker_label)
        root.addWidget(template_card)

        output_card = Card("3. 输出设置")
        self.edit_filename = QLineEdit("报表_{{序号}}.xlsx")
        self.edit_filename.setToolTip(
            "支持 {{列名}}、{{序号}}、{{模板名}}、{{数据文件名}}；"
            "不带 .xlsx 会自动补全")
        output_card.add(labeled_row("文件名模板", self.edit_filename))
        filename_hint = QLabel(
            "例如：{{姓名}}_通知书.xlsx。文件名中的 / \\ : * ? 等非法字符会自动替换。")
        filename_hint.setObjectName("HintLabel")
        filename_hint.setWordWrap(True)
        output_card.add(filename_hint)

        self.cb_skip_empty = QCheckBox("跳过完全为空的数据行")
        self.cb_skip_empty.setChecked(True)
        output_card.add(self.cb_skip_empty)

        self.output_picker = PathPicker("dir", "选择报表输出目录")
        self.output_picker.set_path(default_output_path("模板填充输出"))
        output_card.add(labeled_row("输出目录", self.output_picker))
        root.addWidget(output_card)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.btn_run = QPushButton("开始生成")
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

        self.btn_scan.clicked.connect(self._scan_markers)
        self.busy_changed.connect(self._on_busy)

    def _on_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_run.setText("生成中…" if busy else "开始生成")
        self.btn_scan.setEnabled(not busy)

    def _scan_markers(self) -> None:
        template_path = self.template_picker.path()
        if not template_path:
            self.log_message.emit("请先选择 Excel 模板文件", "warn")
            return
        try:
            markers = scan_template_markers(template_path)
        except Exception as exc:  # noqa: BLE001
            self.report_exception(exc, "检测模板")
            return

        if not markers:
            self.marker_label.setText(
                "模板中没有找到 {{标记}}，请在单元格里写 {{列名}}。")
            self.log_message.emit(
                "模板中没有找到 {{标记}}，请检查模板内容。", "warn")
            return

        text = f"检测到 {len(markers)} 个标记：{'、'.join(markers)}"
        data_path = self.data_picker.path()
        if data_path:
            try:
                columns, sheet_name = read_data_columns(data_path)
            except Exception as exc:  # noqa: BLE001
                self.log_message.emit(
                    f"⚠ 数据源列名读取失败：{exc}", "warn")
            else:
                missing = [marker for marker in markers
                           if marker not in columns
                           and marker not in {"序号", "模板名", "数据文件名"}]
                text += f"\n数据工作表：{sheet_name}；数据列：{'、'.join(columns)}"
                if missing:
                    text += f"\n⚠ 以下标记没有对应列：{'、'.join(missing)}"
                else:
                    text += "\n✔ 所有模板标记都能在数据列中找到。"
        self.marker_label.setText(text)
        self.log_message.emit(f"模板标记：{'、'.join(markers)}", "info")

    def _run(self) -> None:
        data_path = self.data_picker.path()
        template_path = self.template_picker.path()
        output = self.output_picker.path()
        if not data_path:
            self.log_message.emit("请选择数据源文件", "warn")
            return
        if not template_path:
            self.log_message.emit("请选择 Excel 模板文件", "warn")
            return
        if not output:
            self.log_message.emit("请选择输出目录", "warn")
            return

        self.log_message.emit("开始模板填充", "info")
        self.run_task(
            fill_template_reports,
            data_path, template_path, output,
            filename_template=self.edit_filename.text().strip()
            or "报表_{{序号}}.xlsx",
            skip_empty_rows=self.cb_skip_empty.isChecked(),
        )

    def to_scheme(self) -> dict:
        return {
            "data_path": self.data_picker.path(),
            "template_path": self.template_picker.path(),
            "filename_template": self.edit_filename.text(),
            "skip_empty": self.cb_skip_empty.isChecked(),
            "output": self.output_picker.path(),
        }

    def apply_scheme(self, data: dict) -> None:
        self.data_picker.set_path(scheme_str(data, "data_path", ""))
        self.template_picker.set_path(
            scheme_str(data, "template_path", ""))
        self.edit_filename.setText(
            scheme_str(data, "filename_template", "报表_{{序号}}.xlsx"))
        self.cb_skip_empty.setChecked(
            scheme_bool(data, "skip_empty", True))
        self.output_picker.set_path(
            scheme_str(data, "output", self.output_picker.path()))
