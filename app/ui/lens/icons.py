"""纯代码绘制的矢量图标，避免额外图片资源与高分屏模糊。"""
from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPixmap)

from .theme import ACCENT, MINT


def _pen(color: QColor, width: float) -> QPen:
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def draw_logo(painter: QPainter, rect: QRectF) -> None:
    """蓝绿渐变圆角方块 + 白色表格 + 一点星光。"""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(rect, rect.width() * 0.28, rect.height() * 0.28)
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor("#5c8bff"))
    gradient.setColorAt(0.55, QColor("#4a6df0"))
    gradient.setColorAt(1.0, QColor("#39c9a6"))
    painter.fillPath(path, gradient)

    # 顶部高光
    shine = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    shine.setColorAt(0.0, QColor(255, 255, 255, 80))
    shine.setColorAt(0.55, QColor(255, 255, 255, 0))
    painter.fillPath(path, shine)

    # 2x2 表格单元格，尺寸很小时也能看清
    inner = rect.adjusted(rect.width() * 0.22, rect.height() * 0.24,
                          -rect.width() * 0.22, -rect.height() * 0.24)
    gap = max(1.0, rect.width() * 0.055)
    cell_w = (inner.width() - gap) / 2
    cell_h = (inner.height() - gap) / 2
    radius = max(1.0, rect.width() * 0.035)
    painter.setPen(Qt.NoPen)
    for row in range(2):
        for column in range(2):
            alpha = 246 if (row + column) % 2 == 0 else 214
            painter.setBrush(QColor(255, 255, 255, alpha))
            painter.drawRoundedRect(
                QRectF(inner.left() + column * (cell_w + gap),
                       inner.top() + row * (cell_h + gap),
                       cell_w, cell_h), radius, radius)

    # 星光
    cx = rect.right() - rect.width() * 0.15
    cy = rect.top() + rect.height() * 0.16
    r = max(1.4, rect.width() * 0.085)
    painter.setBrush(QColor(255, 255, 255, 242))
    _star(painter, QPointF(cx, cy), r)
    painter.restore()


def _star(painter: QPainter, center: QPointF, radius: float,
          points: int = 4, inner_ratio: float = 0.28) -> None:
    path = QPainterPath()
    for index in range(points * 2):
        angle = -math.pi / 2 + index * math.pi / points
        value = radius if index % 2 == 0 else radius * inner_ratio
        point = QPointF(center.x() + math.cos(angle) * value,
                        center.y() + math.sin(angle) * value)
        if index == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    painter.drawPath(path)


def paint_icon(painter: QPainter, kind: str, rect: QRectF,
               color: QColor, width: float = 1.7,
               accent: QColor | None = None) -> None:
    """在 rect（建议 24x24 等比例）内绘制指定图标。"""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(rect.topLeft())
    scale = min(rect.width(), rect.height()) / 24.0
    painter.scale(scale, scale)
    painter.setPen(_pen(color, width))
    painter.setBrush(Qt.NoBrush)
    accent = accent or color

    if kind == "merge":
        _draw_merge(painter, color, accent, width)
    elif kind == "split":
        _draw_split(painter, color, accent, width)
    elif kind == "clean":
        _draw_clean(painter, color, accent, width)
    elif kind == "advanced":
        painter.drawLine(QPointF(6.5, 17.5), QPointF(17.0, 7.0))
        painter.drawLine(QPointF(10.5, 7.0), QPointF(17.0, 7.0))
        painter.drawLine(QPointF(17.0, 7.0), QPointF(17.0, 13.5))
    elif kind == "close":
        painter.drawLine(QPointF(7.0, 7.0), QPointF(17.0, 17.0))
        painter.drawLine(QPointF(17.0, 7.0), QPointF(7.0, 17.0))
    elif kind == "collapse":
        painter.drawLine(QPointF(14.5, 6.5), QPointF(8.5, 12.0))
        painter.drawLine(QPointF(8.5, 12.0), QPointF(14.5, 17.5))
    elif kind == "expand":
        painter.drawLine(QPointF(9.5, 6.5), QPointF(15.5, 12.0))
        painter.drawLine(QPointF(15.5, 12.0), QPointF(9.5, 17.5))
    elif kind == "plus":
        painter.drawLine(QPointF(12.0, 5.5), QPointF(12.0, 18.5))
        painter.drawLine(QPointF(5.5, 12.0), QPointF(18.5, 12.0))
    elif kind == "file":
        path = QPainterPath()
        path.moveTo(6.0, 3.5)
        path.lineTo(14.0, 3.5)
        path.lineTo(19.0, 8.5)
        path.lineTo(19.0, 20.5)
        path.lineTo(6.0, 20.5)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(14.0, 3.5), QPointF(14.0, 8.5))
        painter.drawLine(QPointF(14.0, 8.5), QPointF(19.0, 8.5))
        painter.drawLine(QPointF(9.0, 13.0), QPointF(16.0, 13.0))
        painter.drawLine(QPointF(9.0, 16.5), QPointF(16.0, 16.5))
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(3.5, 7.0)
        path.lineTo(9.2, 7.0)
        path.lineTo(11.2, 9.4)
        path.lineTo(20.5, 9.4)
        path.lineTo(20.5, 19.0)
        path.lineTo(3.5, 19.0)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "check":
        painter.drawLine(QPointF(5.5, 12.5), QPointF(10.0, 17.0))
        painter.drawLine(QPointF(10.0, 17.0), QPointF(18.5, 7.5))
    elif kind == "warning":
        path = QPainterPath()
        path.moveTo(12.0, 4.0)
        path.lineTo(21.0, 19.5)
        path.lineTo(3.0, 19.5)
        path.closeSubpath()
        painter.drawPath(path)
        painter.drawLine(QPointF(12.0, 9.5), QPointF(12.0, 14.0))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(12.0, 16.8), 0.9, 0.9)
    elif kind == "drag":
        painter.drawLine(QPointF(12.0, 4.0), QPointF(12.0, 20.0))
        painter.drawLine(QPointF(4.0, 12.0), QPointF(20.0, 12.0))
        for point, dx, dy in (
                (QPointF(12.0, 4.0), -2.4, 2.6),
                (QPointF(12.0, 20.0), -2.4, -2.6),
                (QPointF(4.0, 12.0), 2.6, -2.4),
                (QPointF(20.0, 12.0), -2.6, -2.4)):
            painter.drawLine(point, QPointF(point.x() + dx, point.y() + dy))
    elif kind == "lock":
        painter.drawRoundedRect(QRectF(5.5, 10.5, 13.0, 10.0), 2.5, 2.5)
        path = QPainterPath()
        path.moveTo(8.5, 10.5)
        path.lineTo(8.5, 8.0)
        path.cubicTo(8.5, 3.8, 15.5, 3.8, 15.5, 8.0)
        path.lineTo(15.5, 10.5)
        painter.drawPath(path)
        painter.drawLine(QPointF(12.0, 14.5), QPointF(12.0, 17.0))
    elif kind == "spark":
        _star(painter, QPointF(12.0, 11.0), 7.0, 4, 0.3)
        _star(painter, QPointF(19.0, 18.0), 3.0, 4, 0.3)
    elif kind == "grid":
        for row in range(2):
            for column in range(2):
                painter.drawRoundedRect(
                    QRectF(4.5 + column * 8.2, 4.5 + row * 8.2, 6.2, 6.2),
                    1.6, 1.6)
    elif kind == "extract":
        _sheet(painter, QRectF(3.5, 3.0, 10.5, 17.0))
        painter.drawLine(QPointF(6.2, 8.5), QPointF(11.3, 8.5))
        painter.drawLine(QPointF(6.2, 12.0), QPointF(11.3, 12.0))
        painter.drawLine(QPointF(6.2, 15.5), QPointF(9.3, 15.5))
        painter.setPen(_pen(accent, width))
        painter.drawLine(QPointF(14.2, 17.0), QPointF(21.0, 17.0))
        painter.drawLine(QPointF(18.4, 14.4), QPointF(21.0, 17.0))
        painter.drawLine(QPointF(18.4, 19.6), QPointF(21.0, 17.0))
    elif kind == "pivot":
        for row in range(2):
            for column in range(2):
                cell = QRectF(3.5 + column * 9.0, 3.5 + row * 9.0, 7.6, 7.6)
                if row == 0 and column == 1:
                    painter.setBrush(QColor(accent.red(), accent.green(),
                                            accent.blue(), 42))
                    painter.setPen(_pen(accent, width))
                    painter.drawRoundedRect(cell, 1.8, 1.8)
                    painter.setPen(_pen(color, width))
                    painter.setBrush(Qt.NoBrush)
                else:
                    painter.drawRoundedRect(cell, 1.8, 1.8)
    elif kind == "convert":
        painter.drawLine(QPointF(3.8, 8.0), QPointF(19.4, 8.0))
        painter.drawLine(QPointF(16.8, 5.4), QPointF(19.4, 8.0))
        painter.drawLine(QPointF(16.8, 10.6), QPointF(19.4, 8.0))
        painter.drawLine(QPointF(20.2, 16.0), QPointF(4.6, 16.0))
        painter.drawLine(QPointF(7.2, 13.4), QPointF(4.6, 16.0))
        painter.drawLine(QPointF(7.2, 18.6), QPointF(4.6, 16.0))
    elif kind == "flow":
        painter.drawRoundedRect(QRectF(3.0, 4.0, 6.0, 5.0), 1.4, 1.4)
        painter.drawRoundedRect(QRectF(15.0, 3.5, 6.0, 6.0), 1.4, 1.4)
        painter.drawRoundedRect(QRectF(9.0, 15.5, 6.0, 5.0), 1.4, 1.4)
        painter.drawLine(QPointF(6.0, 9.0), QPointF(6.0, 12.4))
        painter.drawLine(QPointF(6.0, 12.4), QPointF(18.0, 12.4))
        painter.drawLine(QPointF(18.0, 12.4), QPointF(18.0, 9.5))
        painter.drawLine(QPointF(12.0, 12.4), QPointF(12.0, 15.5))
        painter.setPen(_pen(accent, width))
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 26))
        painter.drawEllipse(QPointF(12.0, 12.4), 1.5, 1.5)
    elif kind == "about":
        painter.drawEllipse(QRectF(4.0, 4.0, 16.0, 16.0))
        painter.setBrush(color)
        painter.drawEllipse(QPointF(12.0, 8.2), 0.9, 0.9)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(QPointF(12.0, 11.2), QPointF(12.0, 16.2))
    else:
        painter.drawEllipse(QRectF(5.0, 5.0, 14.0, 14.0))
    painter.restore()


def _sheet(painter: QPainter, rect: QRectF) -> None:
    painter.drawRoundedRect(rect, 1.8, 1.8)
    painter.drawLine(QPointF(rect.left() + 1.5, rect.top() + rect.height() * 0.36),
                     QPointF(rect.right() - 1.5, rect.top() + rect.height() * 0.36))


def _draw_merge(painter: QPainter, color: QColor, accent: QColor,
                width: float) -> None:
    _sheet(painter, QRectF(3.0, 3.2, 7.0, 7.2))
    _sheet(painter, QRectF(14.0, 3.2, 7.0, 7.2))
    # 中央向下箭头：两份文档汇入一张总表
    painter.drawLine(QPointF(12.0, 10.6), QPointF(12.0, 14.4))
    painter.drawLine(QPointF(9.6, 12.2), QPointF(12.0, 14.6))
    painter.drawLine(QPointF(14.4, 12.2), QPointF(12.0, 14.6))
    painter.setPen(_pen(accent, width))
    painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 26))
    painter.drawRoundedRect(QRectF(5.2, 16.0, 13.6, 4.6), 1.8, 1.8)


def _draw_split(painter: QPainter, color: QColor, accent: QColor,
                width: float) -> None:
    _sheet(painter, QRectF(8.0, 2.8, 8.0, 6.0))
    painter.setPen(_pen(color, width))
    targets = (4.6, 12.0, 19.4)
    for target in targets:
        path = QPainterPath(QPointF(12.0, 9.0))
        path.cubicTo(12.0, 12.0, target, 11.0, target, 14.2)
        painter.drawPath(path)
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 24))
        painter.setPen(_pen(accent, width))
        painter.drawRoundedRect(QRectF(target - 2.4, 15.0, 4.8, 5.4), 1.4, 1.4)
        painter.setPen(_pen(color, width))
        painter.setBrush(Qt.NoBrush)


def _draw_clean(painter: QPainter, color: QColor, accent: QColor,
                width: float) -> None:
    _sheet(painter, QRectF(4.2, 3.0, 13.5, 17.0))
    painter.drawLine(QPointF(7.0, 10.0), QPointF(14.0, 10.0))
    painter.drawLine(QPointF(7.0, 13.0), QPointF(12.3, 13.0))
    painter.drawLine(QPointF(7.0, 16.0), QPointF(10.8, 16.0))
    painter.setPen(_pen(accent, max(1.2, width * 0.9)))
    _star(painter, QPointF(18.4, 15.2), 4.6, 4, 0.3)
    _star(painter, QPointF(14.3, 20.2), 2.2, 4, 0.32)


def icon_pixmap(kind: str, size: int, color: QColor,
                width: float = 1.7) -> QPixmap:
    """供 QLabel / QPushButton 使用的图标位图（含 2x 高分屏）。"""
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    paint_icon(painter, kind, QRectF(0, 0, size * 2, size * 2),
               color, width * 2)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return pixmap


__all__ = ["paint_icon", "draw_logo", "icon_pixmap", "ACCENT", "MINT"]
