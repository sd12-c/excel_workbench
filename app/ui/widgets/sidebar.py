"""左侧导航栏：与悬浮透镜一致的矢量图标导航。"""
from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter
from PyQt5.QtWidgets import (QAbstractButton, QButtonGroup, QHBoxLayout,
                             QLabel, QSizePolicy, QVBoxLayout, QWidget)

from app.config import APP_VERSION
from app.ui.lens.icons import paint_icon
from app.ui.lens.theme import ACCENT, font
from app.ui.widgets.brand import BrandLogo


class NavButton(QAbstractButton):
    """图标 + 文字的导航按钮，和透镜动作按钮同一套绘制方式。"""

    def __init__(self, text: str, kind: str, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._kind = kind
        self._hover = False
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(188, 40)

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        checked = self.isChecked()

        if checked:
            fill = QLinearGradient(rect.topLeft(), rect.topRight())
            fill.setColorAt(0.0, QColor(79, 124, 255, 42))
            fill.setColorAt(1.0, QColor(79, 124, 255, 8))
            painter.setPen(QColor(79, 124, 255, 58))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 10, 10)
            # 左侧细指示条
            painter.setPen(Qt.NoPen)
            painter.setBrush(ACCENT)
            painter.drawRoundedRect(
                QRectF(rect.left() + 3, rect.center().y() - 8, 3, 16), 1.5, 1.5)
        elif self._hover:
            painter.setPen(QColor(255, 255, 255, 180))
            painter.setBrush(QColor(255, 255, 255, 135))
            painter.drawRoundedRect(rect, 10, 10)

        icon_rect = QRectF(rect.left() + 14, rect.center().y() - 9, 18, 18)
        icon_color = ACCENT if checked else QColor("#5c6981")
        paint_icon(painter, self._kind, icon_rect, icon_color, 1.8)

        text_color = ACCENT if checked else (
            QColor("#2f5fe0") if self._hover else QColor("#44506a"))
        painter.setFont(font(12, 600 if checked else 400))
        metrics = QFontMetrics(painter.font())
        text_rect = QRectF(rect.left() + 43, rect.top(),
                           rect.width() - 53, rect.height())
        painter.setPen(text_color)
        painter.drawText(
            text_rect, int(Qt.AlignLeft | Qt.AlignVCenter),
            metrics.elidedText(self.text(), Qt.ElideRight,
                               max(20, int(text_rect.width()))))


class Sidebar(QWidget):
    page_changed = pyqtSignal(int)

    ITEMS = [
        ("流水线画布", "flow", "拖拽编排合并 / 清洗 / 拆分 / 输出流程"),
        ("合并工作表", "merge", "多文件 / 多工作表合并"),
        ("拆分工作表", "split", "按列分组拆分"),
        ("批量格式化", "clean", "清空行 / 去重 / 日期规范"),
        ("提取与替换", "extract", "提取指定列、批量替换"),
        ("模板填充", "file", "数据源 + 模板，批量生成报表"),
        ("数据透视", "pivot", "选行/列/值，一键生成透视表"),
        ("格式转换", "convert", "CSV ↔ Excel 互转 / 编码选择"),
        ("关于", "about", "版本信息 / 功能说明 / 更新日志"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(216)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(5)

        # 品牌区
        brand = QWidget()
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(4, 0, 0, 14)
        brand_layout.setSpacing(10)

        icon = BrandLogo(36)
        icon.setObjectName("BrandIcon")
        brand_layout.addWidget(icon, 0, Qt.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        title = QLabel("Excel 工作台")
        title.setObjectName("BrandTitle")
        subtitle = QLabel("LENS CONSOLE")
        subtitle.setObjectName("BrandSub")
        text_box.addWidget(title)
        text_box.addWidget(subtitle)
        brand_layout.addLayout(text_box, 1)
        layout.addWidget(brand)

        # 导航按钮
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = []
        for index, (text, kind, tip) in enumerate(self.ITEMS):
            button = NavButton(text, kind)
            button.setToolTip(tip)
            button.clicked.connect(
                lambda _checked, i=index: self.page_changed.emit(i))
            self._group.addButton(button, index)
            self._buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)

        footer = QLabel(f"v{APP_VERSION}  ·  LENS EDITION")
        footer.setObjectName("SidebarFooter")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
