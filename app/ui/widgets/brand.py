"""与悬浮透镜一致的品牌图标。"""
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget

from app.ui.lens.icons import draw_logo


class BrandLogo(QWidget):
    def __init__(self, size: int = 36, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        draw_logo(painter, QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
