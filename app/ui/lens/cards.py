"""文件预览卡片、结果卡片与横向卡片带。"""
from __future__ import annotations

import math
import os
import subprocess

from PyQt5.QtCore import (QMimeData, QPoint, QPointF, QRectF, Qt, QTimer,
                          QUrl, QVariantAnimation, pyqtSignal)
from PyQt5.QtGui import (QColor, QDrag, QFontMetrics, QLinearGradient,
                         QPainter, QPen)
from PyQt5.QtWidgets import QFrame, QMenu, QScrollArea, QWidget

from .controls import (IconButton, TinyLink, draw_elided, draw_two_lines,
                       rounded_path)
from .icons import paint_icon
from .theme import (ACCENT, CARD_GAP, CARD_H, CARD_W, DANGER, FAINT, INK,
                    INK_SOFT, MINT, MUTED, SUCCESS, font)


def _format_size(size: int) -> str:
    value = float(max(0, size))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class FileCard(QWidget):
    """单个 Excel 的微缩预览卡片。"""

    preview_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.name = os.path.basename(path)
        self.extension = os.path.splitext(self.name)[1].lower().lstrip(".")
        self.columns: list[str] = []
        self.rows: list[list[str]] = []
        self.sheets: list[str] = []
        self.error = ""
        self._loading = True
        self._hover = False
        self._remove_hover = False
        self._shimmer = 0.0
        self._reveal = 1.0
        self._setup_ui()
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(75)
        self._shimmer_timer.timeout.connect(self._tick_shimmer)
        self._shimmer_timer.start()
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(360)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_reveal)

    def _setup_ui(self) -> None:
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self.path)
        self.setMouseTracking(True)

    def play_reveal(self, delay_ms: int = 0) -> None:
        self._reveal = 0.0
        self._anim.stop()
        QTimer.singleShot(max(0, delay_ms), self._start_reveal)

    def _start_reveal(self) -> None:
        self._anim.start()

    def _on_reveal(self, value) -> None:
        self._reveal = float(value)
        self.update()

    def set_brief(self, payload: dict) -> None:
        self.columns = [str(item) for item in payload.get("columns", [])]
        self.rows = [[str(cell) for cell in row]
                     for row in payload.get("rows", [])]
        self.sheets = [str(item) for item in payload.get("sheets", [])]
        self.error = str(payload.get("error", "") or "")
        self._loading = False
        self._shimmer_timer.stop()
        if self.error:
            self.setToolTip(f"{self.path}\n读取表头失败：{self.error}")
        else:
            columns = "、".join(self.columns[:6])
            self.setToolTip(
                f"{self.path}\n{len(self.sheets) or 1} 个工作表\n列：{columns}")
        self.update()

    def _tick_shimmer(self) -> None:
        self._shimmer = (self._shimmer + 0.09) % 1.0
        self.update()

    def _remove_rect(self) -> QRectF:
        return QRectF(self.width() - 27, 7, 20, 20)

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self._remove_hover = False
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        hover = self._remove_rect().contains(event.pos())
        if hover != self._remove_hover:
            self._remove_hover = hover
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and (
                self._remove_hover or self._remove_rect().contains(event.pos())):
            self.remove_requested.emit(self.path)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.preview_requested.emit(self.path)
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        menu = QMenu(self)
        preview = menu.addAction("预览前 20 行")
        locate = menu.addAction("在文件夹中显示")
        menu.addSeparator()
        remove = menu.addAction("从透镜中移除")
        chosen = menu.exec_(event.globalPos())
        if chosen is preview:
            self.preview_requested.emit(self.path)
        elif chosen is locate:
            try:
                os.startfile(os.path.dirname(self.path))  # noqa: S606
            except OSError:
                pass
        elif chosen is remove:
            self.remove_requested.emit(self.path)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setOpacity(max(0.0, min(1.0, self._reveal)))
        offset = (1.0 - self._reveal) * 16.0
        painter.translate(0, offset)
        lifted = self._hover or self._reveal < 0.999
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._hover:
            rect.translate(0, -2)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(45, 60, 95, 18 if not self._hover else 30))
        painter.drawRoundedRect(rect.translated(0, 2), 16, 16)

        fill = QColor(255, 255, 255, 170 if self._hover else 138)
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 16, 16)
        border = QColor(255, 255, 255, 200) if not self._hover else \
            QColor(79, 124, 255, 100)
        painter.setPen(border)
        painter.drawRoundedRect(rect, 16, 16)

        # 顶部图标 + 扩展名
        badge = QRectF(rect.left() + 11, rect.top() + 11, 28, 28)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(226, 248, 240, 230))
        painter.drawRoundedRect(badge, 9, 9)
        paint_icon(painter, "file", badge.adjusted(7, 6, -7, -6),
                   QColor("#20a97c"), 1.5)

        painter.setFont(font(7.5, 700, 0.8))
        painter.setPen(FAINT)
        painter.drawText(
            QRectF(rect.left() + 44, rect.top() + 12, rect.width() - 76, 12),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            (self.extension or "excel").upper())

        if self._hover:
            circle = self._remove_rect()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 235) if not self._remove_hover
                             else QColor(DANGER.red(), DANGER.green(),
                                         DANGER.blue(), 36))
            painter.drawEllipse(circle)
            paint_icon(painter, "close", circle.adjusted(5.5, 5.5, -5.5, -5.5),
                       DANGER if self._remove_hover else MUTED, 1.6)

        # 文件名（最多两行）
        draw_two_lines(
            painter,
            QRectF(rect.left() + 12, rect.top() + 45,
                   rect.width() - 24, 32),
            self.name, font(11, 600), INK, max_lines=2)

        # 迷你表格
        table = QRectF(rect.left() + 12, rect.top() + 80,
                       rect.width() - 24, 56)
        self._paint_table(painter, table)

        # 底部信息
        meta = ""
        if self.error:
            meta = "表头读取失败"
        elif self._loading:
            meta = "正在读取表头…"
        else:
            column_count = len(self.columns)
            sheet_count = len(self.sheets) or 1
            meta = f"{column_count} 列 · {sheet_count} 个工作表"
        painter.setFont(font(8.5, 500))
        painter.setPen(DANGER if self.error else MUTED)
        painter.drawText(
            QRectF(rect.left() + 12, rect.bottom() - 22,
                   rect.width() - 24, 14),
            int(Qt.AlignLeft | Qt.AlignVCenter), meta)

        if self.error:
            painter.setPen(Qt.NoPen)
            painter.setBrush(DANGER)
            painter.drawEllipse(QPointF(rect.right() - 17,
                                        rect.bottom() - 15), 2.5, 2.5)
        elif not self._loading:
            painter.setPen(Qt.NoPen)
            painter.setBrush(SUCCESS)
            painter.drawEllipse(QPointF(rect.right() - 17,
                                        rect.bottom() - 15), 2.5, 2.5)

    def _paint_table(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 150))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor(52, 70, 105, 22))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 8, 8)

        if self._loading:
            painter.setPen(Qt.NoPen)
            for row in range(3):
                for column in range(3):
                    cell = QRectF(rect.left() + 6 + column * 41,
                                  rect.top() + 8 + row * 15,
                                  34, 7)
                    wave = (math.sin((self._shimmer + column * 0.2 +
                                      row * 0.12) * math.pi * 2) + 1) / 2
                    painter.setBrush(QColor(150, 166, 195,
                                            int(28 + wave * 45)))
                    painter.drawRoundedRect(cell, 3, 3)
            return

        if self.error or not self.columns:
            painter.setFont(font(8, 500))
            painter.setPen(FAINT)
            painter.drawText(rect, int(Qt.AlignCenter),
                             "无法读取表头" if self.error else "暂无预览")
            return

        columns = self.columns[:3]
        extra = max(0, len(self.columns) - 3)
        count = len(columns)
        header_h = 18.0
        row_h = (rect.height() - header_h - 4) / 2.0
        gap = 0.0
        cell_w = (rect.width() - 8 - gap * (count - 1)) / max(1, count)
        header_font = font(7.5, 600)
        cell_font = font(7, 400)

        painter.save()
        clip = rounded_path(rect.adjusted(1, 1, -1, -1), 7)
        painter.setClipPath(clip)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(79, 124, 255, 24))
        painter.drawRect(QRectF(rect.left() + 4, rect.top() + 4,
                                rect.width() - 8, header_h))

        for index, column in enumerate(columns):
            x = rect.left() + 4 + index * (cell_w + gap)
            header_rect = QRectF(x + 2, rect.top() + 4, cell_w - 4, header_h)
            text = str(column)
            if index == count - 1 and extra:
                text = f"{text} +{extra}"
            draw_elided(painter, header_rect, text, header_font,
                        QColor("#47557a"), Qt.AlignLeft | Qt.AlignVCenter)

        for row_index in range(2):
            if row_index >= len(self.rows):
                break
            row = self.rows[row_index]
            y = rect.top() + 4 + header_h + row_index * row_h
            for index in range(count):
                value = row[index] if index < len(row) else ""
                cell = QRectF(rect.left() + 4 + index * (cell_w + gap),
                              y, cell_w, row_h)
                draw_elided(painter, cell.adjusted(2, 0, -2, 0), value,
                            cell_font, QColor("#7a8499"),
                            Qt.AlignLeft | Qt.AlignVCenter)

        painter.setPen(QColor(52, 70, 105, 20))
        line_y = rect.top() + 4 + header_h
        painter.drawLine(QPointF(rect.left() + 4, line_y),
                         QPointF(rect.right() - 4, line_y))
        painter.restore()


class AddCard(QWidget):
    """卡片带末尾的「添加文件」虚线卡片。"""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(74, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 120 if self._hover else 65))
        painter.drawRoundedRect(rect, 16, 16)

        pen = QPen(QColor(79, 124, 255, 140 if self._hover
                          else 85))
        pen.setWidthF(1.4)
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern([4, 4])
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 16, 16)

        center = rect.center()
        circle = QRectF(center.x() - 16, center.y() - 30, 32, 32)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(79, 124, 255, 28))
        painter.drawEllipse(circle)
        paint_icon(painter, "plus", circle.adjusted(9, 9, -9, -9),
                   ACCENT, 1.8)
        painter.setFont(font(9.5, 500))
        painter.setPen(ACCENT if self._hover else MUTED)
        painter.drawText(
            QRectF(rect.left(), center.y() + 10, rect.width(), 20),
            int(Qt.AlignCenter), "添加")


class CardStrip(QScrollArea):
    """横向排列的预览卡片带，支持滚轮横向滚动。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setWidgetResizable(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(CARD_H + 18)
        self.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:horizontal{background:transparent;height:6px;"
            "margin:2px 2px 0 2px;}"
            "QScrollBar::handle:horizontal{background:rgba(112,132,172,115);"
            "border-radius:3px;min-width:44px;}"
            "QScrollBar::handle:horizontal:hover{background:rgba(79,124,255,150);}"
            "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal"
            "{width:0;height:0;}"
            "QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal"
            "{background:transparent;}")
        self.viewport().setAutoFillBackground(False)

        self._container = QWidget()
        self._container.setStyleSheet("background:transparent;")
        self._container.setFixedHeight(CARD_H + 6)
        self.setWidget(self._container)
        self._cards: list[FileCard] = []
        self._add_card = AddCard(self._container)
        self._add_card.clicked.connect(self._emit_add)

    add_requested = pyqtSignal()

    def _emit_add(self) -> None:
        self.add_requested.emit()

    def cards(self) -> list[FileCard]:
        return list(self._cards)

    def clear(self) -> None:
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        self._layout_cards()

    def add_card(self, card: FileCard) -> None:
        card.setParent(self._container)
        card.show()
        self._cards.append(card)
        self._layout_cards()
        card.play_reveal(30 + (len(self._cards) - 1) * 45)

    def remove_card(self, card: FileCard) -> None:
        if card in self._cards:
            self._cards.remove(card)
            card.setParent(None)
            card.deleteLater()
            self._layout_cards()

    def _layout_cards(self) -> None:
        x = 0
        for card in self._cards:
            card.move(x, 2)
            x += CARD_W + CARD_GAP
        self._add_card.move(x, 2)
        self._add_card.show()
        total = x + self._add_card.width() + 2
        self._container.setFixedWidth(max(total, self.viewport().width()))
        self._container.updateGeometry()
        bar = self.horizontalScrollBar()
        bar.setPageStep(max(1, self.viewport().width()))
        bar.setSingleStep(CARD_W // 2)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._layout_cards()

    def wheelEvent(self, event):  # noqa: N802
        delta = event.angleDelta().y() or event.angleDelta().x()
        bar = self.horizontalScrollBar()
        bar.setValue(bar.value() - delta)
        event.accept()


class ResultCard(QWidget):
    """处理完成后的发光结果卡片，可拖到文件夹 / 微信 / WPS。"""

    open_requested = pyqtSignal(str)
    close_requested = pyqtSignal()
    drag_started = pyqtSignal()
    drag_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(448, 146)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("按住卡片，拖到文件夹、微信或 WPS 中")
        self._path = ""
        self._is_folder = False
        self._title = ""
        self._meta = ""
        self._hint = "按住卡片，拖到文件夹 / 微信 / WPS"
        self._phase = 0.0
        self._hover = False
        self._press_pos: QPoint | None = None
        self._dragging = False

        self._timer = QTimer(self)
        self._timer.setInterval(55)
        self._timer.timeout.connect(self._tick)

        self.btn_close = IconButton("close", 22, MUTED, self)
        self.btn_close.clicked.connect(self.close_requested.emit)
        self.btn_open = TinyLink("打开所在位置", "folder", self)
        self.btn_open.clicked.connect(self._open_location)

    def showEvent(self, event):  # noqa: N802
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def resizeEvent(self, event):  # noqa: N802
        if hasattr(self, "btn_close"):
            self.btn_close.move(self.width() - 36, 10)
            self.btn_open.move(self.width() - 142, self.height() - 38)
        super().resizeEvent(event)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.045) % (math.pi * 2)
        self.update()

    def set_result(self, path: str, stats: dict | None,
                   action: str) -> None:
        self._path = path
        self._is_folder = os.path.isdir(path)
        self._hint = ("按住卡片，拖到文件夹 / 资源管理器"
                      if self._is_folder
                      else "按住卡片，拖到文件夹 / 微信 / WPS")
        stats = stats or {}
        if self._is_folder:
            self._title = os.path.basename(os.path.normpath(path))
            count = int(stats.get("files", 0) or 0)
            failed = int(stats.get("failed", 0) or 0)
            failed_note = f" · {failed} 个读取失败" if failed else ""
            if action == "split":
                self._meta = (f"已生成 {count} 个文件 · 每个 Sheet 独立保存"
                              + failed_note)
            else:
                self._meta = (f"已清洗 {count} 个文件 · 原文件保持不变"
                              + failed_note)
        else:
            self._title = os.path.basename(path)
            try:
                size_text = _format_size(os.path.getsize(path))
            except OSError:
                size_text = ""
            if action == "merge":
                rows = int(stats.get("rows", 0) or 0)
                cols = int(stats.get("cols", 0) or 0)
                files = int(stats.get("files", 0) or 0)
                failed = int(stats.get("failed", 0) or 0)
                self._meta = (f"{rows:,} 行 × {cols} 列 · {files} 个文件"
                              + (f" · {failed} 个读取失败" if failed else "")
                              + (f" · {size_text}" if size_text else ""))
            else:
                self._meta = size_text
        self.setToolTip(f"{path}\n{self._hint}")
        self.update()

    # ------------------------------------------------------------ 操作
    def _open_path(self) -> None:
        if not self._path:
            return
        try:
            os.startfile(self._path)  # noqa: S606
        except OSError:
            pass

    def _open_location(self) -> None:
        if not self._path:
            return
        try:
            if self._is_folder:
                os.startfile(self._path)  # noqa: S606
            else:
                subprocess.Popen(
                    ["explorer", "/select,", os.path.normpath(self._path)])
        except OSError:
            pass

    def enterEvent(self, event):  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self._dragging = False
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if (self._press_pos is not None
                and event.buttons() & Qt.LeftButton
                and not self._dragging
                and (event.pos() - self._press_pos).manhattanLength() >= 8):
            self._start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.setCursor(Qt.OpenHandCursor)
            if not self._dragging and self._press_pos is not None:
                self._open_path()
            self._press_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        if not self._path or not os.path.exists(self._path):
            return
        self._dragging = True
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self._path)])
        mime.setText(self._path)
        drag = QDrag(self)
        drag.setMimeData(mime)
        pixmap = self.grab()
        scaled = pixmap.scaled(int(pixmap.width() * 0.62),
                               int(pixmap.height() * 0.62),
                               Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
        drag.setPixmap(scaled)
        drag.setHotSpot(QPoint(int(scaled.width() * 0.3),
                               int(scaled.height() * 0.45)))
        self.drag_started.emit()
        drag.exec_(Qt.CopyAction)
        self._press_pos = None
        self.setCursor(Qt.OpenHandCursor)
        self.drag_finished.emit()

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        card = QRectF(self.rect()).adjusted(10, 8, -10, -14)
        radius = 18.0
        breathe = (math.sin(self._phase) + 1) / 2
        glow_alpha = int(26 + breathe * 20)

        # 淡绿色光晕
        for index in range(1, 7):
            alpha = max(2, int(glow_alpha * (1 - index / 7.0)))
            pen = QPen(QColor(52, 205, 145, alpha))
            pen.setWidthF(2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                card.adjusted(-index, -index, index, index),
                radius + index, radius + index)

        # 卡片主体
        gradient = QLinearGradient(card.topLeft(), card.bottomRight())
        gradient.setColorAt(0.0, QColor(255, 255, 255, 246))
        gradient.setColorAt(0.55, QColor(248, 255, 252, 232))
        gradient.setColorAt(1.0, QColor(233, 251, 244, 224))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(card, radius, radius)

        painter.setPen(QColor(47, 191, 130, 150 if self._hover else 110))
        painter.drawRoundedRect(card, radius, radius)
        painter.setPen(QColor(255, 255, 255, 190))
        painter.drawRoundedRect(card.adjusted(1, 1, -1, -1),
                                radius - 1, radius - 1)

        # 左侧图标
        icon_box = QRectF(card.left() + 18, card.center().y() - 25, 50, 50)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(214, 247, 234, 235))
        painter.drawRoundedRect(icon_box, 14, 14)
        paint_icon(painter, "folder" if self._is_folder else "file",
                   icon_box.adjusted(13, 12, -13, -12),
                   QColor("#1fa97c"), 1.8)

        text_left = icon_box.right() + 16
        text_width = card.width() - (text_left - card.left()) - 92
        painter.setFont(font(13, 700))
        painter.setPen(INK)
        metrics = QFontMetrics(painter.font())
        painter.drawText(
            QRectF(text_left, card.top() + 18, text_width, 20),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            metrics.elidedText(self._title, Qt.ElideMiddle,
                               max(20, int(text_width))))
        painter.setFont(font(9.5, 500))
        painter.setPen(MUTED)
        painter.drawText(
            QRectF(text_left, card.top() + 40, text_width, 16),
            int(Qt.AlignLeft | Qt.AlignVCenter),
            metrics.elidedText(self._meta, Qt.ElideRight,
                               max(20, int(text_width))))

        # 拖拽提示
        hint_rect = QRectF(text_left, card.top() + 62, text_width, 18)
        painter.setFont(font(9, 600))
        painter.setPen(QColor(31, 169, 124, 235))
        paint_icon(painter, "drag",
                   QRectF(hint_rect.left(), hint_rect.top() + 2, 13, 13),
                   QColor(31, 169, 124, 225), 1.4)
        painter.drawText(
            hint_rect.adjusted(18, 0, 0, 0),
            int(Qt.AlignLeft | Qt.AlignVCenter), self._hint)

        # 右上角细小的完成标记
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(52, 205, 145, int(120 + breathe * 50)))
        painter.drawEllipse(QPointF(card.right() - 30,
                                    card.top() + 15), 2.2, 2.2)
