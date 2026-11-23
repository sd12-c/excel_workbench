"""透镜内的自绘控件：按钮、开关、投放区、环形进度等。"""
from __future__ import annotations

import math

from PyQt5.QtCore import (QEasingCurve, QPointF, QPropertyAnimation, QRectF,
                          QSize, Qt, QTimer, pyqtProperty, pyqtSignal)
from PyQt5.QtGui import (QColor, QFontMetrics, QLinearGradient, QPainter,
                         QPainterPath, QPen)
from PyQt5.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout, QWidget)

from .icons import draw_logo, paint_icon
from .theme import (ACCENT, ACCENT_DEEP, DANGER, FAINT, INK, INK_SOFT, MINT,
                    MUTED, SUCCESS, font)


# --------------------------------------------------------------------------- #
# 绘制小工具
# --------------------------------------------------------------------------- #
def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def draw_elided(painter: QPainter, rect: QRectF, text: str,
                qfont, color: QColor,
                align: int = Qt.AlignLeft | Qt.AlignVCenter) -> None:
    painter.save()
    painter.setFont(qfont)
    painter.setPen(color)
    metrics = QFontMetrics(qfont)
    value = metrics.elidedText(str(text), Qt.ElideRight,
                               max(10, int(rect.width())))
    painter.drawText(rect, int(align), value)
    painter.restore()


def draw_two_lines(painter: QPainter, rect: QRectF, text: str,
                   qfont, color: QColor, max_lines: int = 2) -> None:
    """最多两行、末行省略的文件名排版。"""
    painter.save()
    painter.setFont(qfont)
    painter.setPen(color)
    metrics = QFontMetrics(qfont)
    width = max(12, int(rect.width()))
    remaining = str(text)
    lines = []
    while remaining and len(lines) < max_lines:
        if metrics.horizontalAdvance(remaining) <= width:
            lines.append(remaining)
            remaining = ""
            break
        cut = len(remaining)
        while cut > 1 and metrics.horizontalAdvance(remaining[:cut]) > width:
            cut -= 1
        # 尽量在分隔符处断行
        split_at = cut
        for index in range(cut, max(2, cut - 10), -1):
            if remaining[index - 1] in " _-—·":
                split_at = index
                break
        lines.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining and lines:
        lines[-1] = metrics.elidedText(
            lines[-1] + "…" + remaining, Qt.ElideRight, width)
    line_height = metrics.height() + 1
    y = rect.top()
    for line in lines:
        painter.drawText(QRectF(rect.left(), y, width, line_height),
                         int(Qt.AlignLeft | Qt.AlignVCenter), line)
        y += line_height
    painter.restore()


# --------------------------------------------------------------------------- #
# 按钮
# --------------------------------------------------------------------------- #
class SoftButton(QAbstractButton):
    """胶囊按钮：primary / ghost / soft 三种风格。"""

    def __init__(self, text: str = "", variant: str = "ghost",
                 icon: str | None = None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._variant = variant
        self._icon = icon
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(30)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)

    def sizeHint(self) -> QSize:
        qfont = font(11, 600)
        metrics = QFontMetrics(qfont)
        width = metrics.horizontalAdvance(self.text()) + 30
        if self._icon:
            width += 20
        if self._variant == "primary":
            width += 10
        return QSize(max(66, width), 32)

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
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(11.0, rect.height() / 2)
        enabled = self.isEnabled()
        pressed = self.isDown()

        if self._variant == "primary":
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            if not enabled:
                gradient.setColorAt(0.0, QColor("#c3cee6"))
                gradient.setColorAt(1.0, QColor("#b5c2dd"))
            elif pressed:
                gradient.setColorAt(0.0, QColor("#3357d6"))
                gradient.setColorAt(1.0, QColor("#2947b9"))
            elif self._hover:
                gradient.setColorAt(0.0, QColor("#6b95ff"))
                gradient.setColorAt(1.0, QColor("#4471f4"))
            else:
                gradient.setColorAt(0.0, QColor("#5a86ff"))
                gradient.setColorAt(1.0, QColor("#3d6bf0"))
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(rect, radius, radius)
            painter.setPen(QColor(255, 255, 255, 70))
            painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6),
                                    radius, radius)
            text_color = QColor("#ffffff")
        elif self._variant == "soft":
            if self._hover:
                painter.setBrush(QColor(255, 255, 255, 90))
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(rect, radius, radius)
            text_color = MUTED if enabled else FAINT
        else:
            fill = QColor(255, 255, 255, 120 if not self._hover else 180)
            if pressed:
                fill = QColor(236, 242, 255, 210)
            painter.setPen(QColor(255, 255, 255, 150 if self._hover
                                  else 110))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, radius, radius)
            if self._hover:
                painter.setPen(QColor(79, 124, 255, 90))
                painter.drawRoundedRect(rect, radius, radius)
            text_color = ACCENT_DEEP if self._hover else INK_SOFT
            if not enabled:
                text_color = FAINT

        qfont = font(11, 600)
        metrics = QFontMetrics(qfont)
        text_width = metrics.horizontalAdvance(self.text())
        icon_width = 16 if self._icon else 0
        gap = 5 if self._icon else 0
        total = text_width + icon_width + gap
        start = (rect.width() - total) / 2
        if self._icon:
            icon_rect = QRectF(start, rect.center().y() - 7, 14, 14)
            paint_icon(painter, self._icon, icon_rect, text_color, 1.7)
            start += icon_width + gap
        painter.setFont(qfont)
        painter.setPen(text_color)
        painter.drawText(
            QRectF(start, rect.top(), text_width + 2, rect.height()),
            int(Qt.AlignLeft | Qt.AlignVCenter), self.text())


class IconButton(QAbstractButton):
    """圆形 / 方形图标小按钮。"""

    def __init__(self, kind: str, size: int = 28, tint: QColor | None = None,
                 parent=None):
        super().__init__(parent)
        self._kind = kind
        self._hover = False
        self._tint = tint or INK_SOFT
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.update()

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
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._hover:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 150))
            painter.drawEllipse(rect)
        painter.setOpacity(0.55 if not self._hover else 0.95)
        icon_rect = rect.adjusted(rect.width() * 0.26, rect.height() * 0.26,
                                  -rect.width() * 0.26, -rect.height() * 0.26)
        paint_icon(painter, self._kind, icon_rect, self._tint,
                   max(1.4, rect.width() * 0.075))


class TinyLink(QAbstractButton):
    """极简文字链（可带图标）。"""

    def __init__(self, text: str, icon: str | None = None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._icon = icon
        self._hover = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(22)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(font(10))
        width = metrics.horizontalAdvance(self.text()) + 4
        if self._icon:
            width += 16
        return QSize(width, 22)

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
        color = ACCENT_DEEP if self._hover else MUTED
        qfont = font(10, 600 if self._hover else 400)
        metrics = QFontMetrics(qfont)
        text_width = metrics.horizontalAdvance(self.text())
        total = text_width + (14 if self._icon else 0)
        start = (self.width() - total) / 2
        y = (self.height() - 14) / 2
        if self._icon:
            paint_icon(painter, self._icon, QRectF(start, y, 13, 13),
                       color, 1.5)
            start += 15
        painter.setFont(qfont)
        painter.setPen(color)
        painter.drawText(QRectF(start, 0, text_width + 2, self.height()),
                         int(Qt.AlignLeft | Qt.AlignVCenter), self.text())


class TogglePill(QAbstractButton):
    """文字 + 滑动开关的一体化胶囊。"""

    def __init__(self, text: str, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._pos = 1.0 if checked else 0.0
        self._hover = False
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(30)
        self.toggled.connect(self._animate)
        metrics = QFontMetrics(font(10.5, 500))
        self._text_width = metrics.horizontalAdvance(text)
        self.setFixedWidth(self._text_width + 62)

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = float(value)
        self.update()

    knob = pyqtProperty(float, _get_knob, _set_knob)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

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
        rect = QRectF(self.rect()).adjusted(0.5, 1.5, -0.5, -1.5)
        checked = self.isChecked()
        fill = QColor(255, 255, 255, 150 if self._hover else 110)
        if checked:
            fill = QColor(232, 239, 255, 205)
        painter.setPen(QColor(255, 255, 255, 160) if not checked
                       else QColor(79, 124, 255, 90))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 10, 10)

        painter.setFont(font(10.5, 500))
        painter.setPen(INK_SOFT if checked else MUTED)
        painter.drawText(
            QRectF(12, rect.top(), self._text_width + 2, rect.height()),
            int(Qt.AlignLeft | Qt.AlignVCenter), self.text())

        track_w, track_h = 28.0, 16.0
        track = QRectF(rect.right() - track_w - 8,
                       rect.center().y() - track_h / 2, track_w, track_h)
        track_color = ACCENT if checked else QColor(174, 185, 207, 200)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(track, track_h / 2, track_h / 2)

        knob_size = track_h - 4
        knob_x = track.left() + 2 + self._pos * (track_w - knob_size - 4)
        knob = QRectF(knob_x, track.center().y() - knob_size / 2,
                      knob_size, knob_size)
        painter.setBrush(QColor(30, 45, 80, 35))
        painter.drawEllipse(knob.translated(0, 1))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(knob)

        if checked:
            check_rect = QRectF(knob.center().x() - 3.5,
                                knob.center().y() - 3.5, 7, 7)
            paint_icon(painter, "check", check_rect, ACCENT, 1.4)


class ActionButton(QAbstractButton):
    """三大动作卡片按钮。"""

    KINDS = {
        "merge": ("合并汇总", "多文件 → 一张总表", QColor("#4f7cff"),
                  QColor(232, 239, 255)),
        "split": ("按 Sheet 拆分", "每张表 → 独立文件", QColor("#25b894"),
                  QColor(227, 250, 243)),
        "clean": ("批量清洗", "空行 · 空格 · 格式", QColor("#e89a36"),
                  QColor(255, 244, 226)),
    }

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        title, caption, color, soft = self.KINDS[kind]
        self.kind = kind
        self._title = title
        self._caption = caption
        self._color = color
        self._soft = soft
        self._hover = False
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMinimumHeight(86)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

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
        if not self.isEnabled():
            painter.setOpacity(0.52)
        lift = -1.5 if self._hover or self.isChecked() else 0.0
        rect = QRectF(self.rect()).adjusted(1, 1 + lift, -1, -1 + lift)
        checked = self.isChecked()

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(45, 60, 95, 16))
        painter.drawRoundedRect(rect.translated(0, 2), 16, 16)

        fill = QColor(255, 255, 255, 190 if self._hover else 140)
        if checked:
            fill = QColor(self._soft.red(), self._soft.green(),
                          self._soft.blue(), 210)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 16, 16)

        border = QColor(self._color.red(), self._color.green(),
                        self._color.blue(), 150 if checked else
                        (90 if self._hover else 45))
        painter.setPen(border)
        painter.drawRoundedRect(rect, 16, 16)

        icon_bg = QRectF(rect.left() + 13, rect.center().y() - 20, 40, 40)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._color.red(), self._color.green(),
                                self._color.blue(), 30 if checked else 22))
        painter.drawRoundedRect(icon_bg, 12, 12)
        icon_rect = icon_bg.adjusted(9, 9, -9, -9)
        paint_icon(painter, self.kind, icon_rect, self._color, 1.8)

        text_left = icon_bg.right() + 12
        painter.setFont(font(12.5, 700))
        painter.setPen(INK)
        painter.drawText(
            QRectF(text_left, rect.top() + 18, rect.width() - (text_left - rect.left()) - 8, 20),
            int(Qt.AlignLeft | Qt.AlignVCenter), self._title)
        painter.setFont(font(9, 400))
        painter.setPen(MUTED)
        painter.drawText(
            QRectF(text_left, rect.top() + 40, rect.width() - (text_left - rect.left()) - 8, 16),
            int(Qt.AlignLeft | Qt.AlignVCenter), self._caption)

        if checked:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._color)
            painter.drawEllipse(QPointF(rect.right() - 14,
                                        rect.top() + 13), 3.0, 3.0)


# --------------------------------------------------------------------------- #
# 开关条
# --------------------------------------------------------------------------- #
class OptionBar(QWidget):
    """一行极简参数：开关 + 提示 + 开始按钮。"""

    start_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 8, 7)
        layout.setSpacing(10)

        self.toggle_source = TogglePill("来源列", True)
        self.toggle_rename = TogglePill("冲突重命名", True)
        self.hint = QLabel("")
        self.hint.setFont(font(10))
        self.hint.setStyleSheet("color:#6d7890;background:transparent;")
        self.btn_start = SoftButton("开始合并", "primary")
        self.btn_start.setMinimumHeight(30)
        self.btn_start.setFixedHeight(30)
        self.btn_start.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_start.clicked.connect(self.start_clicked.emit)

        layout.addWidget(self.toggle_source)
        layout.addWidget(self.toggle_rename)
        layout.addWidget(self.hint, 1)
        layout.addStretch(1)
        layout.addWidget(self.btn_start)

    def configure(self, action: str) -> None:
        merge = action == "merge"
        self.toggle_source.setVisible(merge)
        self.toggle_rename.setVisible(merge)
        self.hint.setVisible(not merge)
        if action == "merge":
            self.btn_start.setText("开始合并")
            self.hint.setText("")
        elif action == "split":
            self.hint.setText("每张工作表输出为独立 .xlsx 文件")
            self.btn_start.setText("开始拆分")
        else:
            self.hint.setText("清空行 · 去空格 · 统一数字与日期")
            self.btn_start.setText("开始清洗")
        self.btn_start.setFixedWidth(max(96, self.btn_start.sizeHint().width()))

    def set_busy(self, busy: bool) -> None:
        self.toggle_source.setEnabled(not busy)
        self.toggle_rename.setEnabled(not busy)
        self.btn_start.setEnabled(not busy)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QColor(255, 255, 255, 140))
        painter.setBrush(QColor(255, 255, 255, 105))
        painter.drawRoundedRect(rect, 13, 13)
        painter.setPen(QColor(47, 60, 92, 18))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 12, 12)


# --------------------------------------------------------------------------- #
# 投放区
# --------------------------------------------------------------------------- #
class DropZone(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self._active = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(55)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(250)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        if active:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.08) % (math.pi * 2)
        self.update()

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        active = self._active
        pulse = (math.sin(self._phase) + 1) / 2 if active else 0

        fill = QColor(255, 255, 255, 100 if not self._hover else 140)
        if active:
            fill = QColor(79, 124, 255, int(22 + pulse * 22))
        painter.setBrush(fill)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 22, 22)

        pen = QPen(QColor(79, 124, 255, int(120 + pulse * 100))
                   if active else QColor(120, 140, 178, 105))
        pen.setWidthF(1.6)
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern([5.0, 5.0])
        pen.setDashOffset(-self._phase * 12 if active else 0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 21, 21)

        center = QPointF(rect.center().x(), rect.top() + rect.height() * 0.34)
        icon_size = 54
        icon_rect = QRectF(center.x() - icon_size / 2,
                           center.y() - icon_size / 2, icon_size, icon_size)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(79, 124, 255, 22 if not active else 34))
        painter.drawEllipse(icon_rect.adjusted(-11, -11, 11, 11))
        self._paint_tray(painter, icon_rect,
                         ACCENT if not active else ACCENT_DEEP)

        title = "松手放入" if active else "把 Excel 拖到这里"
        painter.setFont(font(17, 600))
        painter.setPen(INK)
        painter.drawText(
            QRectF(rect.left(), icon_rect.bottom() + 16, rect.width(), 26),
            int(Qt.AlignCenter), title)

        painter.setFont(font(10.5))
        painter.setPen(MUTED)
        painter.drawText(
            QRectF(rect.left(), icon_rect.bottom() + 44, rect.width(), 20),
            int(Qt.AlignCenter),
            "立即生成表头预览卡片 · 支持一次拖入多个文件")

        chip_text = "xlsx   xls   xlsm"
        chip_rect = QRectF(rect.center().x() - 88, icon_rect.bottom() + 76,
                           176, 24)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 130))
        painter.drawRoundedRect(chip_rect, 12, 12)
        painter.setFont(font(9, 500, 1.0))
        painter.setPen(FAINT)
        painter.drawText(chip_rect, int(Qt.AlignCenter), chip_text)

        painter.setFont(font(10))
        painter.setPen(ACCENT_DEEP if self._hover else FAINT)
        painter.drawText(
            QRectF(rect.left(), rect.bottom() - 34, rect.width(), 20),
            int(Qt.AlignCenter),
            "或点击选择文件")

    @staticmethod
    def _paint_tray(painter: QPainter, rect: QRectF, color: QColor) -> None:
        pen = QPen(color)
        pen.setWidthF(2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        cx = rect.center().x()
        top = rect.top() + 8
        bottom = rect.center().y() + 5
        painter.drawLine(QPointF(cx, top), QPointF(cx, bottom))
        painter.drawLine(QPointF(cx - 7, bottom - 7), QPointF(cx, bottom))
        painter.drawLine(QPointF(cx + 7, bottom - 7), QPointF(cx, bottom))
        path = QPainterPath(QPointF(rect.left() + 6, rect.center().y() + 10))
        path.lineTo(rect.left() + 6, rect.bottom() - 9)
        path.quadTo(rect.left() + 6, rect.bottom() - 5,
                    rect.left() + 10, rect.bottom() - 5)
        path.lineTo(rect.right() - 10, rect.bottom() - 5)
        path.quadTo(rect.right() - 6, rect.bottom() - 5,
                    rect.right() - 6, rect.bottom() - 9)
        path.lineTo(rect.right() - 6, rect.center().y() + 10)
        painter.drawPath(path)


# --------------------------------------------------------------------------- #
# 环形进度
# --------------------------------------------------------------------------- #
class RingProgress(QWidget):
    def __init__(self, size: int = 92, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._value = 0.0
        self._indeterminate = False
        self._phase = 0.0
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._tick)

    def _get_value(self) -> float:
        return self._value

    def _set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, float(value)))
        self.update()

    value = pyqtProperty(float, _get_value, _set_value)

    def set_value(self, value: float, animate: bool = True) -> None:
        value = max(0.0, min(1.0, float(value)))
        self._anim.stop()
        if animate:
            self._anim.setStartValue(self._value)
            self._anim.setEndValue(value)
            self._anim.start()
        else:
            self._set_value(value)

    def set_indeterminate(self, enabled: bool) -> None:
        self._indeterminate = enabled
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()
            self.update()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.05) % 1.0
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        size = min(self.width(), self.height())
        rect = QRectF(7, 7, size - 14, size - 14)
        center = rect.center()
        radius = rect.width() / 2

        painter.setPen(QPen(QColor(255, 255, 255, 160), 7))
        painter.drawEllipse(rect.adjusted(3.5, 3.5, -3.5, -3.5))

        painter.setPen(QPen(QColor(198, 210, 232, 130), 6))
        painter.drawArc(rect, 0, 360 * 16)

        if self._indeterminate:
            span = 100 * 16
            start = int((90 - self._phase * 360) * 16)
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, ACCENT)
            gradient.setColorAt(1.0, MINT)
            pen = QPen(gradient, 6)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, start, span)
        else:
            progress = self._value
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, ACCENT)
            gradient.setColorAt(0.6, QColor("#5aa8ff"))
            gradient.setColorAt(1.0, MINT)
            glow_pen = QPen(QColor(79, 220, 180, 50), 12)
            glow_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(glow_pen)
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * progress))
            pen = QPen(gradient, 6)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, int(-360 * 16 * progress))
            if progress > 0.01:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor("#ffffff"))
                angle = math.radians(90 - 360 * progress)
                painter.drawEllipse(
                    QPointF(center.x() + math.cos(angle) * radius,
                            center.y() - math.sin(angle) * radius), 4.0, 4.0)

        painter.setFont(font(20 if self._indeterminate else 16, 700))
        painter.setPen(INK)
        painter.drawText(
            QRectF(rect.left(), rect.top() - 1, rect.width(), rect.height()),
            int(Qt.AlignCenter),
            "…" if self._indeterminate else
            f"{int(round(self._value * 100))}%")

        painter.setFont(font(9, 500))
        painter.setPen(MUTED)
        painter.drawText(
            QRectF(rect.left(), rect.center().y() + 10, rect.width(), 16),
            int(Qt.AlignCenter), "处理中")


# --------------------------------------------------------------------------- #
# 侧边收起态
# --------------------------------------------------------------------------- #
class SideTab(QWidget):
    """窄窄一条的悬浮标签：Logo + 竖排「Excel工作台」。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = False
        self._badge = 0
        self._result = False
        self._dark = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_dark(self, dark: bool) -> None:
        if self._dark != dark:
            self._dark = bool(dark)
            self.update()

    def set_badge(self, count: int, has_result: bool = False) -> None:
        self._badge = max(0, int(count))
        self._result = bool(has_result)
        self.update()

    def set_hover(self, hover: bool) -> None:
        if self._hover != hover:
            self._hover = hover
            self.update()

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        width = self.width()
        logo_size = 24
        logo_rect = QRectF((width - logo_size) / 2, 15, logo_size, logo_size)
        painter.setOpacity(1.0 if self._hover else 0.82)
        draw_logo(painter, logo_rect)
        painter.setOpacity(1.0)

        # 左侧三颗小圆点：提示这个标签可以按住拖动
        if self._dark:
            grip_color = QColor(235, 241, 252, 155 if self._hover else 95)
        else:
            grip_color = QColor(60, 74, 102, 145 if self._hover else 85)
        painter.setPen(Qt.NoPen)
        painter.setBrush(grip_color)
        for index in range(3):
            painter.drawEllipse(QPointF(8.5, 43 + index * 4.5), 1.25, 1.25)

        painter.save()
        painter.setFont(font(9.5, 600, 0.5))
        if self._dark:
            painter.setPen(QColor(235, 241, 252,
                                  180 if not self._hover else 245))
        else:
            painter.setPen(QColor(60, 74, 102,
                                  172 if not self._hover else 235))
        metrics = QFontMetrics(painter.font())
        text = "Excel工作台"
        text_width = metrics.horizontalAdvance(text)
        painter.translate(width / 2 + metrics.ascent() / 2 - 1,
                          self.height() - 34)
        painter.rotate(-90)
        painter.drawText(QRectF(0, 0, text_width + 4, metrics.height()),
                         int(Qt.AlignCenter), text)
        painter.restore()

        if self._result:
            painter.setPen(Qt.NoPen)
            painter.setBrush(SUCCESS)
            painter.drawEllipse(QPointF(width / 2, self.height() - 18), 4, 4)
            painter.setBrush(QColor(47, 191, 130, 60))
            painter.drawEllipse(QPointF(width / 2, self.height() - 18), 8, 8)
        elif self._badge:
            badge_rect = QRectF(width / 2 - 9, self.height() - 28, 18, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(ACCENT)
            painter.drawEllipse(badge_rect)
            painter.setFont(font(8, 700))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(badge_rect, int(Qt.AlignCenter),
                             str(min(self._badge, 99)))


# --------------------------------------------------------------------------- #
# 处理中视图
# --------------------------------------------------------------------------- #
class ProcessingView(QWidget):
    cancel_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(26)
        layout.addStretch(1)

        self.ring = RingProgress(96)
        layout.addWidget(self.ring, 0, Qt.AlignVCenter)

        text_box = QWidget()
        text_box.setFixedWidth(300)
        text_layout = QHBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(4)
        self.title = QLabel("正在处理…")
        self.title.setFont(font(14, 700))
        self.title.setStyleSheet("color:#172033;background:transparent;")
        self.subtitle = QLabel("")
        self.subtitle.setFont(font(10.5))
        self.subtitle.setStyleSheet("color:#6d7890;background:transparent;")
        self.subtitle.setWordWrap(True)
        self.cancel = TinyLink("取消任务")
        self.cancel.clicked.connect(self.cancel_requested.emit)
        column_layout.addWidget(self.title)
        column_layout.addWidget(self.subtitle)
        column_layout.addSpacing(2)
        column_layout.addWidget(self.cancel, 0, Qt.AlignLeft)
        text_layout.addWidget(column)
        layout.addWidget(text_box, 0, Qt.AlignVCenter)
        layout.addStretch(1)

    def set_state(self, title: str, subtitle: str) -> None:
        self.title.setText(title)
        self.subtitle.setText(subtitle)

    def set_progress(self, value: float) -> None:
        self.ring.set_value(value)


# --------------------------------------------------------------------------- #
# 错误视图
# --------------------------------------------------------------------------- #
class ErrorView(QWidget):
    retry_requested = pyqtSignal()
    advanced_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 6, 24, 6)
        layout.setSpacing(5)
        layout.addStretch(1)

        badge = QLabel()
        badge.setPixmap(paint_warning_pixmap(34))
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet("background:transparent;")
        layout.addWidget(badge, 0, Qt.AlignHCenter)

        self.title = QLabel("处理没有完成")
        self.title.setFont(font(12.5, 700))
        self.title.setStyleSheet("color:#172033;background:transparent;")
        self.title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title)

        self.detail = QLabel("")
        self.detail.setFont(font(10))
        self.detail.setStyleSheet("color:#6d7890;background:transparent;")
        self.detail.setAlignment(Qt.AlignCenter)
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)

        self.hint = QLabel("")
        self.hint.setFont(font(9.5))
        self.hint.setStyleSheet("color:#98a2b6;background:transparent;")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.btn_retry = SoftButton("重试", "ghost")
        self.btn_retry.clicked.connect(self.retry_requested.emit)
        self.btn_advanced = SoftButton("高级处理", "primary")
        self.btn_advanced.clicked.connect(self.advanced_requested.emit)
        buttons.addWidget(self.btn_retry)
        buttons.addWidget(self.btn_advanced)
        buttons.addStretch(1)
        layout.addSpacing(8)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def set_error(self, title: str, detail: str = "", hint: str = "") -> None:
        self.title.setText(title or "处理没有完成")
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.hint.setText(hint)
        self.hint.setVisible(bool(hint))


def paint_warning_pixmap(size: int):
    from PyQt5.QtGui import QPixmap
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(2, 2)
    rect = QRectF(2, 2, size - 4, size - 4)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(226, 85, 99, 26))
    painter.drawEllipse(rect)
    paint_icon(painter, "warning",
               QRectF(size * 0.27, size * 0.27, size * 0.46, size * 0.46),
               DANGER, 1.7)
    painter.end()
    pixmap.setDevicePixelRatio(2.0)
    return pixmap
