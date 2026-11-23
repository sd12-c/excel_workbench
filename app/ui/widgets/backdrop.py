"""高级工作台 / 预览对话框使用的柔和玻璃背景。

不抓取桌面，直接用低饱和的蓝紫 / 薄荷色渐变与柔光叠加，
与悬浮透镜的毛玻璃面板保持同一套视觉语言。
"""
from __future__ import annotations

import random

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (QColor, QImage, QLinearGradient, QPainter, QPixmap,
                         QRadialGradient)
from PyQt5.QtWidgets import QWidget


class SoftBackdrop(QWidget):
    """带柔光与细颗粒的浅色玻璃背景。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SoftBackdrop")
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._noise = self._build_noise()

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        width = max(1.0, rect.width())
        height = max(1.0, rect.height())

        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, QColor("#eef5ff"))
        base.setColorAt(0.42, QColor("#e9effb"))
        base.setColorAt(0.72, QColor("#e8f1f6"))
        base.setColorAt(1.0, QColor("#e3f3ee"))
        painter.fillRect(rect, base)

        glows = (
            (QPointF(width * 0.12, height * 0.04), width * 0.52,
             QColor(112, 156, 255, 64)),
            (QPointF(width * 0.86, height * 0.08), width * 0.42,
             QColor(190, 160, 255, 42)),
            (QPointF(width * 0.82, height * 0.88), width * 0.52,
             QColor(94, 220, 183, 40)),
            (QPointF(width * 0.18, height * 0.92), width * 0.38,
             QColor(255, 198, 150, 26)),
        )
        for center, radius, color in glows:
            glow = QRadialGradient(center, radius)
            glow.setColorAt(0.0, color)
            glow.setColorAt(0.55, QColor(color.red(), color.green(),
                                         color.blue(), color.alpha() // 3))
            glow.setColorAt(1.0, QColor(color.red(), color.green(),
                                        color.blue(), 0))
            painter.fillRect(rect, glow)

        painter.setOpacity(0.030)
        painter.drawTiledPixmap(self.rect(), self._noise)
        painter.setOpacity(1.0)

        # 很淡的顶部高光，避免整块背景过于平
        top = QLinearGradient(rect.topLeft(),
                              QPointF(rect.left(), rect.top() + 120))
        top.setColorAt(0.0, QColor(255, 255, 255, 110))
        top.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(rect, top)
        painter.end()

    def _build_noise(self) -> QPixmap:
        size = 96
        image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        rng = random.Random(20261123)
        for y in range(size):
            for x in range(size):
                value = rng.randint(0, 255)
                alpha = rng.randint(3, 12)
                image.setPixelColor(x, y, QColor(value, value, value, alpha))
        return QPixmap.fromImage(image)
