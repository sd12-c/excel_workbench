"""关于页面：版本信息、功能说明、更新日志与隐私说明。"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QFrame, QLabel, QScrollArea, QVBoxLayout,
                             QWidget)

from app.config import APP_NAME, APP_SUBTITLE, APP_VERSION
from app.ui.widgets.form_helpers import Card

from .base_page import BasePage

FEATURES = [
    ("合并工作表", "多文件 / 多工作表合并，支持按表头合并或只保留共有列，来源列名称可自定义。"),
    ("拆分工作表", "按列分组拆分，支持自定义文件名模板、过滤空分组。"),
    ("批量格式化", "原子清洗引擎：全局规则 + 单列绑定（手机号 / 金额 / 日期），可保存规则 JSON，并按规则套用数字格式与对齐。"),
    ("提取与替换", "批量提取指定列；导入 Excel 对照表批量替换，正则模式默认关闭。"),
    ("模板填充", "一份数据源 + 一份 xlsx 模板，按 {{姓名}} 等标记循环生成 N 份独立报表，适合通知书、对账单、报价单、邀请函。"),
    ("数据透视", "可视化选择行、列、值和聚合方式（求和 / 计数 / 平均值），一键生成透视表并输出新文件，新手也能完成汇总分析。"),
    ("格式转换", "CSV ↔ Excel 互转，CSV → Excel 支持 UTF-8 / GBK 编码选择。"),
    ("方案保存", "把各页面输出路径与参数保存为 JSON 方案（默认在项目 config 文件夹），下次启动自动加载。"),
    ("通用能力", "表格预览、进度显示、随时停止、输出文件自动避让、友好中文错误提示。"),
]

CHANGELOG = [
    ("v1.1.1", "2026-11-23", [
        "批量格式化：新增通用原子清洗配置引擎，支持全局规则、单列绑定（手机号 / 金额 / 日期）、规则 JSON 保存/加载，以及按绑定规则套用数字格式和对齐方式。",
        "新增模板填充：一份数据源 + 一份 xlsx 模板，按 {{列名}} 标记循环生成 N 份独立报表，支持文件名模板并保留模板样式。",
        "新增数据透视：可视化选择行 / 列 / 值和聚合方式（求和 / 计数 / 平均值），一键生成新的透视表文件。",
        "测试与文档：补充模板填充测试数据，更新功能说明、README、使用指南和测试数据说明。",
    ]),
    ("v1.1.0", "2026-11-21", [
        "合并工作表：新增按表头合并 / 仅保留共有列两种列对齐策略，来源列名称可自定义。",
        "拆分工作表：新增文件名模板与空分组过滤。",
        "批量格式化：新增清除超链接 / 批注、数字格式统一、中文日期自动识别与失败行日志。",
        "提取与替换：支持导入 Excel 对照表批量替换；正则替换默认关闭并增加表达式校验。",
        "格式转换：CSV → Excel 支持 UTF-8 / GBK 编码选择；移除 PDF 导出。",
        "通用：新增表格预览、进度文字、停止任务、输出文件自动避让、路径兼容、方案保存与关于页面。",
    ]),
    ("v1.0.0", "初始版本", [
        "支持合并工作表、拆分工作表、批量格式化、提取与替换、CSV ↔ Excel 转换等基础功能。",
    ]),
]


class AboutPage(BasePage):
    PAGE_TITLE = "关于"
    PAGE_SUBTITLE = "版本信息、功能说明、更新日志与隐私说明"

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

        root.addWidget(self._build_hero())
        root.addWidget(self._build_privacy())
        root.addWidget(self._build_features())
        root.addWidget(self._build_changelog())

        footer = QLabel("完全离线运行 · 数据处理全部在本机完成")
        footer.setObjectName("HintLabel")
        footer.setAlignment(Qt.AlignCenter)
        root.addWidget(footer)
        root.addStretch(1)

        scroll.setWidget(container)
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)

    # ------------------------------------------------------------ 子卡片
    def _build_hero(self) -> Card:
        card = Card()
        title = QLabel(APP_NAME)
        title.setObjectName("AboutTitle")
        subtitle = QLabel(f"版本 v{APP_VERSION}  ·  {APP_SUBTITLE}")
        subtitle.setObjectName("HintLabel")
        guide = QLabel("详细使用指南：项目根目录 / 使用指南.md（PDF：使用指南.pdf）")
        guide.setObjectName("HintLabel")
        card.add(title)
        card.add(subtitle)
        card.add(guide)
        return card

    def _build_privacy(self) -> Card:
        card = Card("隐私与数据安全")
        badge = QLabel("仅本地处理，不上传任何表格文件")
        badge.setObjectName("PrivacyBadge")
        badge.setWordWrap(True)
        detail = QLabel(
            "所有表格文件的读取、合并、拆分、清洗、替换与转换均在本机完成。"
            "本工具不会联网上传文件、不会收集表格内容，处理结果只写入您选择的本地目录。")
        detail.setObjectName("AboutText")
        detail.setWordWrap(True)
        note = QLabel("错误日志仅保存在本机 logs/error.log，用于排查问题，不会上传。")
        note.setObjectName("HintLabel")
        note.setWordWrap(True)
        card.add(badge)
        card.add(detail)
        card.add(note)
        return card

    def _build_features(self) -> Card:
        card = Card("功能说明")
        for name, description in FEATURES:
            label = QLabel(f"<b>{name}</b>　{description}")
            label.setObjectName("AboutText")
            label.setTextFormat(Qt.RichText)
            label.setWordWrap(True)
            card.add(label)
        return card

    def _build_changelog(self) -> Card:
        card = Card("更新日志")
        for version, date_text, items in CHANGELOG:
            title = QLabel(
                f"<b>{version}</b>　"
                f"<span style='color:#8b93a7'>{date_text}</span>")
            title.setTextFormat(Qt.RichText)
            card.add(title)
            for item in items:
                line = QLabel(f"　• {item}")
                line.setObjectName("AboutBullet")
                line.setWordWrap(True)
                card.add(line)
        return card
