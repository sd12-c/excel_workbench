"""左侧导航栏。"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QButtonGroup, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from app.config import APP_SUBTITLE, APP_VERSION


class Sidebar(QWidget):
    page_changed = pyqtSignal(int)

    ITEMS = [
        ("▤  合并工作表", "多文件 / 多工作表合并"),
        ("⑂  拆分工作表", "按列分组拆分"),
        ("⚙  批量格式化", "清空行 / 去重 / 日期规范"),
        ("⌕  提取与替换", "提取指定列、批量替换"),
        ("✎  模板填充", "数据源 + 模板，批量生成报表"),
        ("▦  数据透视", "选行/列/值，一键生成透视表"),
        ("⇄  格式转换", "CSV ↔ Excel 互转 / 编码选择"),
        ("ⓘ  关于", "版本信息 / 功能说明 / 更新日志"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(216)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(6)

        # 品牌区
        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(4, 0, 0, 14)
        brand_layout.setSpacing(10)

        icon = QLabel("X")
        icon.setObjectName("BrandIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(34, 34)
        brand_layout.addWidget(icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        title = QLabel("Excel 批量工作台")
        title.setObjectName("BrandTitle")
        subtitle = QLabel(APP_SUBTITLE.upper())
        subtitle.setObjectName("BrandSub")
        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        brand_layout.addLayout(text_box, 1)
        layout.addWidget(brand)

        # 导航按钮
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = []
        for index, (text, tip) in enumerate(self.ITEMS):
            button = QPushButton(text)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked, i=index: self.page_changed.emit(i))
            self._group.addButton(button, index)
            self._buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)

        footer = QLabel(f"v{APP_VERSION}  ·  Built with PyQt5")
        footer.setObjectName("SidebarFooter")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)