"""悬浮透镜主窗口：收起态 / 悬停展开 / 拖入 / 预览 / 一键处理 / 结果拖出。"""
from __future__ import annotations

import json
import os
import time
from typing import Iterable, List

from PyQt5.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect,
                          QRectF, QSize, Qt, QTimer, QVariantAnimation,
                          pyqtSignal)
from PyQt5.QtGui import (QColor, QCursor, QGuiApplication, QPainter, QPen)
from PyQt5.QtWidgets import (QApplication, QFileDialog, QGraphicsOpacityEffect,
                             QHBoxLayout, QLabel, QMenu, QStackedWidget,
                             QToolTip, QVBoxLayout, QWidget)

from app.config import (APP_NAME, APP_VERSION, LENS_STATE_FILE, OUTPUT_DIR,
                        ensure_output_dir)
from app.core.common import unique_path
from app.core.errors import explain, record_exception
from app.core.excel_engine import collect_files
from app.core.quick_ops import (clean_for_lens, merge_for_lens, split_by_sheet,
                                timestamped_dir, timestamped_file)
from app.workers.task_worker import TaskWorker

from .cards import CardStrip, FileCard, ResultCard
from .controls import (ActionButton, DropZone, ErrorView, IconButton,
                       OptionBar, ProcessingView, SideTab, SoftButton,
                       TinyLink)
from .glass import GlassBackdrop
from .icons import draw_logo, icon_pixmap
from .loader import PreviewLoader
from .theme import (ACCENT, COLLAPSED_H, COLLAPSED_W, EXPANDED_H, EXPANDED_W,
                    FAINT, INK, MUTED, PANEL_RADIUS, font)


class LogoWidget(QWidget):
    def __init__(self, size: int = 30, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        draw_logo(painter, QRectF(self.rect()).adjusted(0, 0, -0.5, -0.5))


class DropHint(QWidget):
    """拖拽悬停时覆盖在内容上的「吸附」提示。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hide()
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(55)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.09) % 6.28
        self.update()

    def paintEvent(self, _event):  # noqa: N802
        import math

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(10, 10, -10, -10)
        pulse = (math.sin(self._phase) + 1) / 2

        # 轻微蓝色氛围，不遮住文件卡片
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(79, 124, 255, int(18 + pulse * 12)))
        painter.drawRoundedRect(rect, 22, 22)
        pen = QPen(QColor(79, 124, 255, int(155 + pulse * 80)))
        pen.setWidthF(2.4)
        pen.setStyle(Qt.CustomDashLine)
        pen.setDashPattern([7, 6])
        pen.setDashOffset(-self._phase * 14)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 20, 20)

        # 居中的吸附提示卡
        badge = QRectF(rect.center().x() - 196, rect.center().y() - 68,
                       392, 136)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(45, 60, 95, 30))
        painter.drawRoundedRect(badge.translated(0, 4), 22, 22)
        painter.setBrush(QColor(251, 253, 255, 246))
        painter.drawRoundedRect(badge, 22, 22)
        painter.setPen(QColor(79, 124, 255, 120))
        painter.drawRoundedRect(badge, 22, 22)

        circle = QRectF(badge.center().x() - 27, badge.top() + 16, 54, 54)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(79, 124, 255, int(24 + pulse * 16)))
        painter.drawEllipse(circle.adjusted(-7, -7, 7, 7))
        DropZone._paint_tray(painter, circle, ACCENT)

        painter.setFont(font(17, 700))
        painter.setPen(INK)
        painter.drawText(
            QRectF(badge.left(), circle.bottom() + 10, badge.width(), 24),
            int(Qt.AlignCenter), "松手放入")
        painter.setFont(font(10))
        painter.setPen(MUTED)
        painter.drawText(
            QRectF(badge.left(), circle.bottom() + 35, badge.width(), 18),
            int(Qt.AlignCenter), "文件会被吸附到透镜 · 立即生成预览卡片")


class LensWindow(QWidget):
    """桌面上的悬浮透镜，标签可拖动并记忆位置。"""

    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Lens")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        self._files: List[str] = []
        self._cards: dict[str, FileCard] = {}
        self._briefs: dict[str, dict] = {}
        self._loaders: List[PreviewLoader] = []
        self._loader_token = 0
        self._worker: TaskWorker | None = None
        self._workbench = None

        self._expanded = False
        self._animating = False
        self._drag_active = False
        self._external_drag = False
        self._active_action = ""
        self._last_action = ""
        self._state = "empty"
        self._result_path = ""
        self._result_stats: dict = {}
        self._task_output = ""
        self._stay_open_until = 0.0
        self._screen = QGuiApplication.screenAt(QCursor.pos()) \
            or QGuiApplication.primaryScreen()
        self._tab_anchor = QPoint()
        self._expand_to_left = True
        self._suppress_hover = False
        self._tab_drag_active = False
        self._tab_drag_moved = False
        self._tab_drag_origin = QPoint()
        self._tab_drag_offset = QPoint()
        self._anchor_changed = False

        self._backdrop = GlassBackdrop()
        self._collapsed_dark = False
        self._success_glow = 0.0
        self._drop_pulse = 0.0
        self._height_anims: dict[str, QPropertyAnimation] = {}
        self._bar_targets: dict[str, bool] = {}

        self._build_ui()
        self._setup_timers()
        self._set_state("empty", animate=False)
        self._restore_anchor()
        self._apply_initial_geometry()
        self.setWindowOpacity(0.78)
        try:
            self._backdrop.refresh(self._collapsed_rect(), None)
        except Exception:  # noqa: BLE001
            pass
        self._update_backdrop_theme()
        self.setContextMenuPolicy(Qt.DefaultContextMenu)

    # ================================================================ 构建界面
    def _build_ui(self) -> None:
        self.content = QWidget(self)
        self.content.setStyleSheet("background:transparent;")
        self.content.setFixedSize(EXPANDED_W, EXPANDED_H)
        root = QVBoxLayout(self.content)
        root.setContentsMargins(24, 20, 24, 16)
        root.setSpacing(10)

        # ---- 顶部标题栏
        header = QWidget()
        header.setFixedHeight(46)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        self.logo = LogoWidget(30)
        header_layout.addWidget(self.logo, 0, Qt.AlignVCenter)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        self.title_label = QLabel("Excel 工作台")
        self.title_label.setFont(font(15, 700))
        self.title_label.setStyleSheet("color:#172033;background:transparent;")
        self.subtitle_label = QLabel("拖入表格，即刻整理")
        self.subtitle_label.setFont(font(9.5))
        self.subtitle_label.setStyleSheet(
            "color:#6d7890;background:transparent;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        header_layout.addLayout(title_box, 1)

        self.btn_advanced = SoftButton("高级", "ghost", "advanced")
        self.btn_advanced.setFixedHeight(28)
        self.btn_advanced.setToolTip("打开完整工作台，使用专业参数")
        self.btn_advanced.clicked.connect(self.open_workbench)
        header_layout.addWidget(self.btn_advanced, 0, Qt.AlignVCenter)

        self.btn_collapse = IconButton("collapse", 28, MUTED)
        self.btn_collapse.setToolTip("收起透镜")
        self.btn_collapse.clicked.connect(self.collapse_now)
        header_layout.addWidget(self.btn_collapse, 0, Qt.AlignVCenter)
        root.addWidget(header)

        # ---- 中部视图栈
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background:transparent;border:none;")
        from PyQt5.QtWidgets import QSizePolicy
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.drop_zone = DropZone()
        self.drop_zone.clicked.connect(self._pick_files)
        self.stack.addWidget(self.drop_zone)

        self.files_page = QWidget()
        files_layout = QVBoxLayout(self.files_page)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(4)
        count_row = QWidget()
        count_layout = QHBoxLayout(count_row)
        count_layout.setContentsMargins(2, 0, 2, 0)
        count_layout.setSpacing(8)
        self.count_label = QLabel("双击卡片预览 · 滚轮横向浏览")
        self.count_label.setFont(font(9, 500))
        self.count_label.setStyleSheet("color:#6d7890;background:transparent;")
        count_layout.addWidget(self.count_label)
        count_layout.addStretch(1)
        self.btn_add_more = TinyLink("添加", "plus")
        self.btn_add_more.clicked.connect(self._pick_files)
        self.btn_clear = TinyLink("清空")
        self.btn_clear.clicked.connect(self._clear_files)
        count_layout.addWidget(self.btn_add_more)
        count_layout.addWidget(self.btn_clear)
        files_layout.addWidget(count_row)

        self.card_strip = CardStrip()
        self.card_strip.add_requested.connect(self._pick_files)
        files_layout.addWidget(self.card_strip, 0)
        files_layout.addStretch(1)
        self.stack.addWidget(self.files_page)

        self.processing_view = ProcessingView()
        self.processing_view.cancel_requested.connect(self._cancel_task)
        self.stack.addWidget(self.processing_view)

        self.result_page = QWidget()
        result_layout = QVBoxLayout(self.result_page)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(2)
        result_layout.addStretch(1)
        self.result_card = ResultCard()
        self.result_card.close_requested.connect(self._dismiss_result)
        self.result_card.drag_started.connect(self._on_result_drag_started)
        self.result_card.drag_finished.connect(self._on_result_drag_finished)
        result_layout.addWidget(self.result_card, 0, Qt.AlignHCenter)
        self.result_hint = QLabel("结果已保存到 out_put，可直接拖走或点击打开")
        self.result_hint.setFont(font(9))
        self.result_hint.setStyleSheet("color:#98a2b6;background:transparent;")
        self.result_hint.setAlignment(Qt.AlignCenter)
        result_layout.addWidget(self.result_hint)
        result_layout.addStretch(1)
        self.stack.addWidget(self.result_page)

        self.error_view = ErrorView()
        self.error_view.retry_requested.connect(self._retry_task)
        self.error_view.advanced_requested.connect(self.open_workbench)
        self.stack.addWidget(self.error_view)

        root.addWidget(self.stack, 1)

        # ---- 三大动作
        self.actions_bar = QWidget()
        actions_layout = QHBoxLayout(self.actions_bar)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        self.action_buttons: dict[str, ActionButton] = {}
        for kind in ("merge", "split", "clean"):
            button = ActionButton(kind)
            button.clicked.connect(
                lambda _checked=False, value=kind: self._on_action(value))
            actions_layout.addWidget(button, 1)
            self.action_buttons[kind] = button
        self.actions_bar.setMaximumHeight(0)
        self.actions_bar.setMinimumHeight(0)
        self.actions_bar.hide()
        root.addWidget(self.actions_bar)

        # ---- 极简参数条
        self.option_bar = OptionBar()
        self.option_bar.start_clicked.connect(self._start_task)
        self.option_bar.setMaximumHeight(0)
        self.option_bar.setMinimumHeight(0)
        self.option_bar.hide()
        root.addWidget(self.option_bar)

        # ---- 底部状态
        footer = QWidget()
        footer.setFixedHeight(16)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(2, 0, 2, 0)
        footer_layout.setSpacing(5)
        lock = QLabel()
        lock.setPixmap(icon_pixmap("lock", 10, FAINT))
        lock.setStyleSheet("background:transparent;")
        footer_layout.addWidget(lock)
        privacy = QLabel("仅在本机处理 · 不上传文件")
        privacy.setFont(font(8.5))
        privacy.setStyleSheet("color:#98a2b6;background:transparent;")
        footer_layout.addWidget(privacy)
        footer_layout.addStretch(1)
        self.footer_status = QLabel(f"v{APP_VERSION}")
        self.footer_status.setFont(font(8.5))
        self.footer_status.setStyleSheet(
            "color:#98a2b6;background:transparent;")
        footer_layout.addWidget(self.footer_status)
        root.addWidget(footer)

        # ---- 收起态
        self.tab = SideTab(self)
        self.tab.hide()

        # ---- 拖拽吸附提示
        self.drop_hint = DropHint(self)

        self._content_fx = QGraphicsOpacityEffect(self.content)
        self._content_fx.setOpacity(0.0)
        self.content.setGraphicsEffect(self._content_fx)
        self._content_anim = QPropertyAnimation(
            self._content_fx, b"opacity", self)
        self._content_anim.setDuration(220)
        self._content_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.content.hide()

    # ================================================================ 几何 / 动画
    def _available_rect(self) -> QRect:
        screen = self._screen or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _collapsed_rect(self) -> QRect:
        return QRect(self._tab_anchor, QSize(COLLAPSED_W, COLLAPSED_H))

    def _expanded_rect(self) -> QRect:
        available = self._available_rect()
        tab = QRect(self._tab_anchor, QSize(COLLAPSED_W, COLLAPSED_H))
        # 标签在右半边向左展开，在左半边向右展开
        self._expand_to_left = tab.center().x() >= available.center().x()
        if self._expand_to_left:
            x = tab.x() + tab.width() - EXPANDED_W
        else:
            x = tab.x()
        max_x = max(available.left() + 8,
                    available.right() - EXPANDED_W - 8)
        x = max(available.left() + 8, min(x, max_x))

        y = tab.center().y() - EXPANDED_H // 2
        max_y = max(available.top() + 8,
                    available.bottom() - EXPANDED_H - 8)
        y = max(available.top() + 8, min(y, max_y))
        return QRect(x, y, EXPANDED_W, EXPANDED_H)

    def _apply_initial_geometry(self) -> None:
        self.setGeometry(self._collapsed_rect())
        self.tab.setGeometry(0, 0, COLLAPSED_W, COLLAPSED_H)
        self.content.setGeometry(self._content_rect())
        self.content.hide()
        self.tab.show()
        self.tab.raise_()
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("按住顶部拖动 · 单击展开 · 悬停下方展开")

    def _content_rect(self) -> QRect:
        x = self.width() - EXPANDED_W if self._expand_to_left else 0
        return QRect(x, (self.height() - EXPANDED_H) // 2,
                     EXPANDED_W, EXPANDED_H)

    # ------------------------------------------------------------ 位置记忆
    def _default_anchor(self) -> QPoint:
        available = self._available_rect()
        point = QPoint(available.right() - COLLAPSED_W - 10,
                       available.top()
                       + (available.height() - COLLAPSED_H) // 2)
        return self._clamp_anchor(point)

    def _clamp_anchor(self, point: QPoint,
                      screen=None) -> QPoint:
        screen = screen or self._screen or QGuiApplication.primaryScreen()
        if screen is None:
            return QPoint(point)
        available = screen.availableGeometry()
        margin = 8
        min_x = available.left() + margin
        min_y = available.top() + margin
        max_x = max(min_x, available.right() - COLLAPSED_W - margin)
        max_y = max(min_y, available.bottom() - COLLAPSED_H - margin)
        return QPoint(max(min_x, min(point.x(), max_x)),
                      max(min_y, min(point.y(), max_y)))

    def _screen_for_point(self, point: QPoint):
        screen = QGuiApplication.screenAt(point)
        if screen is not None:
            return screen
        screens = [item for item in QGuiApplication.screens()
                   if item is not None]
        if not screens:
            return self._screen or QGuiApplication.primaryScreen()

        def distance(item) -> int:
            rect = item.availableGeometry()
            dx = max(rect.left() - point.x(), 0, point.x() - rect.right())
            dy = max(rect.top() - point.y(), 0, point.y() - rect.bottom())
            return dx * dx + dy * dy

        return min(screens, key=distance)

    def _restore_anchor(self) -> None:
        point = self._load_anchor()
        if point is None:
            self._tab_anchor = self._default_anchor()
            return
        screen = self._screen_for_point(point)
        if screen is not None:
            self._screen = screen
        self._tab_anchor = self._clamp_anchor(point, screen)

    def _load_anchor(self) -> QPoint | None:
        try:
            with open(LENS_STATE_FILE, "r", encoding="utf-8-sig") as fp:
                data = json.load(fp)
            x = int(data["x"])
            y = int(data["y"])
        except (OSError, ValueError, TypeError, KeyError):
            return None
        return QPoint(x, y)

    def _save_anchor(self) -> None:
        try:
            directory = os.path.dirname(os.path.abspath(LENS_STATE_FILE))
            os.makedirs(directory, exist_ok=True)
            temp = f"{LENS_STATE_FILE}.tmp"
            with open(temp, "w", encoding="utf-8") as fp:
                json.dump({"x": int(self._tab_anchor.x()),
                           "y": int(self._tab_anchor.y())},
                          fp, ensure_ascii=False, indent=2)
                fp.write("\n")
            os.replace(temp, LENS_STATE_FILE)
        except OSError:
            pass

    def _setup_timers(self) -> None:
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(70)
        self._hover_timer.timeout.connect(self._check_hover)
        self._hover_timer.start()

        self._expand_timer = QTimer(self)
        self._expand_timer.setSingleShot(True)
        self._expand_timer.setInterval(180)
        self._expand_timer.timeout.connect(self._start_expand)

        self._drag_glass_timer = QTimer(self)
        self._drag_glass_timer.setInterval(180)
        self._drag_glass_timer.timeout.connect(self._refresh_tab_backdrop)

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.timeout.connect(self._start_collapse)

        self._geometry_anim = QPropertyAnimation(self, b"geometry", self)
        self._geometry_anim.setDuration(300)
        self._geometry_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._geometry_anim.finished.connect(self._on_geometry_anim_finished)

        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(180)
        self._opacity_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._success_anim = QVariantAnimation(self)
        self._success_anim.setDuration(1600)
        self._success_anim.setKeyValueAt(0.0, 0.0)
        self._success_anim.setKeyValueAt(0.18, 1.0)
        self._success_anim.setKeyValueAt(0.55, 0.72)
        self._success_anim.setKeyValueAt(1.0, 0.0)
        self._success_anim.valueChanged.connect(self._on_success_value)

        self._pulse_anim = QVariantAnimation(self)
        self._pulse_anim.setDuration(520)
        self._pulse_anim.setStartValue(0.0)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.valueChanged.connect(self._on_pulse_value)
        self._pulse_anim.finished.connect(self._on_pulse_finished)

    def _on_geometry_anim_finished(self) -> None:
        self._animating = False
        self._content_geometry()
        if self._expanded:
            self.content.show()
            self.content.raise_()
            self._fade_content_in()
            self.setCursor(Qt.ArrowCursor)
            self.setToolTip("")
        else:
            self._content_anim.stop()
            self._content_fx.setOpacity(0.0)
            self.content.hide()
            self.tab.show()
            self.tab.raise_()
            self.tab.setGeometry(self._tab_rect())
            self._opacity_anim.stop()
            self.setWindowOpacity(0.78)
            self.setCursor(Qt.OpenHandCursor)
            self.setToolTip("按住顶部拖动 · 单击展开 · 悬停下方展开")
            # 收起后重新采样标签当前所在位置，避免沿用展开面板的旧背景
            self._refresh_tab_backdrop()
        self.update()

    def _content_geometry(self) -> None:
        self.content.setGeometry(self._content_rect())
        self.tab.setGeometry(self._tab_rect())
        self.drop_hint.setGeometry(0, 0, self.width(), self.height())

    def _tab_rect(self) -> QRect:
        # 收起 / 展开动画过程中，让标签始终停留在最终的屏幕位置
        anchor = self._collapsed_rect()
        return QRect(anchor.x() - self.x(), anchor.y() - self.y(),
                     COLLAPSED_W, COLLAPSED_H)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self._expanded or self._animating:
            self.content.setGeometry(self._content_rect())
            self.tab.setGeometry(self._tab_rect())
        if self.drop_hint.isVisible():
            self.drop_hint.setGeometry(0, 0, self.width(), self.height())
        self.update()

    def _fade_content_in(self) -> None:
        if not self._expanded:
            return
        self._content_anim.stop()
        self._content_anim.setStartValue(self._content_fx.opacity())
        self._content_anim.setEndValue(1.0)
        self._content_anim.setDuration(220)
        self._content_anim.start()

    def _set_collapsed_opacity(self, hover: bool) -> None:
        target = 0.97 if hover else 0.78
        if abs(self.windowOpacity() - target) < 0.02:
            return
        if (self._opacity_anim.state() == QPropertyAnimation.Running
                and abs(float(self._opacity_anim.endValue()) - target) < 0.001):
            return
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(target)
        self._opacity_anim.start()

    # ================================================================ 悬停 / 展开
    def _check_hover(self) -> None:
        if not self.isVisible():
            return
        if self._tab_drag_active:
            self.tab.set_hover(True)
            return
        if QApplication.activeModalWidget() is not None:
            return
        if QApplication.activePopupWidget() is not None:
            return
        inside = self.frameGeometry().contains(QCursor.pos())
        in_drag_zone = (not self._expanded) and \
            self._drag_zone_rect().contains(QCursor.pos())
        if not self._expanded and not self._animating:
            if self._suppress_hover and not inside:
                self._suppress_hover = False
            self.tab.set_hover(inside)
            self._set_collapsed_opacity(inside)
            if inside:
                self.setCursor(Qt.OpenHandCursor if in_drag_zone
                               else Qt.ArrowCursor)
        if inside:
            self._collapse_timer.stop()
            if (not self._expanded and not self._animating
                    and not self._suppress_hover and not in_drag_zone):
                if not self._expand_timer.isActive():
                    self._expand_timer.start()
            elif in_drag_zone:
                self._expand_timer.stop()
        else:
            self._expand_timer.stop()
            if (self._expanded and not self._animating
                    and self._worker is None and not self._external_drag
                    and time.monotonic() >= self._stay_open_until):
                if not self._collapse_timer.isActive():
                    delay = 4500 if self._files else 900
                    self._collapse_timer.start(delay)

    def expand_now(self) -> None:
        """立即展开（托盘 / 拖拽进入时调用）。"""
        self._stay_open_until = time.monotonic() + 3.0
        self._suppress_hover = False
        self._expand_timer.stop()
        self._collapse_timer.stop()
        self._start_expand()

    def _start_expand(self) -> None:
        if self._expanded or self._animating:
            return
        self._screen = self._screen_for_point(self._tab_anchor) or self._screen
        target = self._expanded_rect()

        # 抓取展开前桌面背景；此时仅有小标签被遮挡，模糊后会自然消失
        self._backdrop.refresh(target, self.geometry())
        self._update_backdrop_theme()

        self._expanded = True
        self._animating = True
        self._suppress_hover = False
        self._expand_timer.stop()
        self.tab.hide()
        self.setCursor(Qt.ArrowCursor)
        self.setToolTip("")
        self.content.setGeometry(self._content_rect())
        self.content.show()
        self.content.raise_()
        self._content_anim.stop()
        self._content_fx.setOpacity(0.0)
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(1.0)
        self._opacity_anim.start()

        self._geometry_anim.stop()
        self._geometry_anim.setStartValue(self.geometry())
        self._geometry_anim.setEndValue(target)
        self._geometry_anim.setDuration(300)
        self._geometry_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._geometry_anim.start()
        QTimer.singleShot(110, self._fade_content_in)

    def _start_collapse(self, force: bool = False) -> None:
        if not self._expanded or self._animating:
            return
        if self._worker is not None and not force:
            return
        if self._external_drag and not force:
            return
        self._collapse_timer.stop()
        self._animating = True
        self._expanded = False
        target = self._collapsed_rect()
        self._suppress_hover = target.contains(QCursor.pos())
        self.tab.setGeometry(self._tab_rect())
        self.tab.show()
        self.tab.raise_()
        self.setCursor(Qt.OpenHandCursor)

        self._content_anim.stop()
        self._content_anim.setStartValue(self._content_fx.opacity())
        self._content_anim.setEndValue(0.0)
        self._content_anim.setDuration(130)
        self._content_anim.start()

        self._geometry_anim.stop()
        self._geometry_anim.setStartValue(self.geometry())
        self._geometry_anim.setEndValue(target)
        self._geometry_anim.setDuration(260)
        self._geometry_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._geometry_anim.start()

        self.drop_hint.stop()
        self._drag_active = False
        self.drop_zone.set_active(False)
        self._opacity_anim.stop()
        self._opacity_anim.setStartValue(self.windowOpacity())
        self._opacity_anim.setEndValue(0.78)
        self._opacity_anim.setDuration(260)
        self._opacity_anim.start()

    def collapse_now(self) -> None:
        self._collapse_timer.stop()
        self._start_collapse(force=True)

    # ================================================================ 绘制
    def paintEvent(self, _event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        ratio = 0.0
        if self.width() > COLLAPSED_W:
            ratio = min(1.0, (self.width() - COLLAPSED_W)
                        / (EXPANDED_W - COLLAPSED_W))
        radius = 20.0 + (PANEL_RADIUS - 20.0) * ratio
        strength = 0.32 + 0.68 * ratio
        tint = None
        if self._drop_active_color():
            tint = QColor(79, 124, 255, 18)
        elif self._success_glow > 0.01:
            tint = QColor(52, 205, 145, int(20 * self._success_glow))
        dark = not self._expanded and self._collapsed_dark
        self._backdrop.paint(painter, rect, radius, strength, tint, dark=dark)

        # 收起态的侧边光带
        if not self._expanded:
            painter.save()
            painter.setPen(QPen(QColor(255, 255, 255, 70 if dark else 135),
                                1.2))
            painter.drawLine(QRectF(rect.left() + 1.2, rect.top() + 22,
                                   0, rect.height() - 44).topLeft(),
                             QRectF(rect.left() + 1.2, rect.top() + 22,
                                   0, rect.height() - 44).bottomLeft())
            painter.restore()

        # 拖拽吸附高亮
        if self._drag_active:
            painter.save()
            painter.setPen(QPen(QColor(79, 124, 255, 150), 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2),
                                    radius - 1, radius - 1)
            painter.restore()

        # 拖入吸附脉冲
        if self._drop_pulse > 0.0:
            progress = self._drop_pulse
            alpha = int(150 * (1.0 - progress))
            inset = 2 + progress * 10
            pen = QPen(QColor(79, 124, 255, alpha))
            pen.setWidthF(2.2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset),
                                    max(8.0, radius - inset),
                                    max(8.0, radius - inset))

        # 成功淡绿光晕
        if self._success_glow > 0.01:
            glow = self._success_glow
            painter.save()
            painter.setBrush(Qt.NoBrush)
            for index in range(1, 15):
                alpha = int(78 * glow * (1.0 - index / 15.0))
                if alpha <= 0:
                    continue
                pen = QPen(QColor(52, 205, 145, alpha))
                pen.setWidthF(2.1)
                painter.setPen(pen)
                painter.drawRoundedRect(
                    rect.adjusted(index, index, -index, -index),
                    max(6.0, radius - index * 0.35),
                    max(6.0, radius - index * 0.35))
            painter.restore()

    def _update_backdrop_theme(self) -> None:
        self._collapsed_dark = self._backdrop.average_color.lightness() < 115
        self.tab.set_dark(self._collapsed_dark)
        self.update()

    def _drop_active_color(self) -> bool:
        return self._drag_active

    def _on_success_value(self, value) -> None:
        self._success_glow = float(value)
        self.update()

    def _on_pulse_value(self, value) -> None:
        self._drop_pulse = float(value)
        self.update()

    def _on_pulse_finished(self) -> None:
        self._drop_pulse = 0.0
        self.update()

    def _play_drop_pulse(self) -> None:
        self._pulse_anim.stop()
        self._pulse_anim.start()

    def _play_success_glow(self) -> None:
        self._success_anim.stop()
        self._success_anim.start()

    # ================================================================ 状态 / 界面更新
    def _set_state(self, state: str, animate: bool = True) -> None:
        self._state = state
        if state == "empty":
            self.stack.setCurrentWidget(self.drop_zone)
            self.drop_zone.set_active(False)
        elif state == "files":
            self.stack.setCurrentWidget(self.files_page)
        elif state == "processing":
            self.stack.setCurrentWidget(self.processing_view)
        elif state == "result":
            self.stack.setCurrentWidget(self.result_page)
        elif state == "error":
            self.stack.setCurrentWidget(self.error_view)
        self._refresh_action_state()
        self._update_subtitle()
        self._update_badge()

    def _refresh_action_state(self) -> None:
        has_files = bool(self._files)
        show_actions = has_files and self._state != "empty"
        self._set_bar_visible(self.actions_bar, show_actions,
                              EXPANDED_W, 86, animate=True)
        show_options = has_files and bool(self._active_action) \
            and self._state in ("files", "result")
        self._set_bar_visible(self.option_bar, show_options,
                              EXPANDED_W, 46, animate=True)
        busy = self._state == "processing"
        for button in self.action_buttons.values():
            button.setEnabled(not busy)
        self.option_bar.set_busy(busy)
        self.btn_clear.setEnabled(not busy)
        self.btn_add_more.setEnabled(not busy)

    def _set_bar_visible(self, widget: QWidget, visible: bool,
                         width: int, height: int, animate: bool = True) -> None:
        key = "actions" if widget is self.actions_bar else "option"
        current = self._height_anims.get(key)
        running = (current is not None
                   and current.state() == QPropertyAnimation.Running)
        if not animate:
            if running:
                current.stop()
            self._bar_targets[key] = visible
            widget.setVisible(visible)
            widget.setMinimumHeight(height if visible else 0)
            widget.setMaximumHeight(height if visible else 0)
            return
        if self._bar_targets.get(key) == visible:
            if running:
                return
            if visible and widget.isVisible() and widget.height() == height:
                return
            if not visible and not widget.isVisible():
                return
        self._bar_targets[key] = visible
        if running:
            current.stop()
        if visible:
            if not widget.isVisible():
                widget.setMaximumHeight(0)
                widget.setMinimumHeight(0)
                widget.show()
            start = widget.height() if widget.isVisible() else 0
            end = height
        else:
            if not widget.isVisible():
                return
            start = widget.height()
            end = 0
        anim = QPropertyAnimation(widget, b"maximumHeight", self)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(max(0, start))
        anim.setEndValue(end)
        anim.finished.connect(
            lambda w=widget, v=visible, h=height: self._on_bar_anim_done(w, v, h))
        self._height_anims[key] = anim
        anim.start()

    def _on_bar_anim_done(self, widget: QWidget, visible: bool,
                          height: int) -> None:
        if visible:
            widget.setMinimumHeight(height)
            widget.setMaximumHeight(height)
        else:
            widget.hide()
            widget.setMinimumHeight(0)
            widget.setMaximumHeight(0)
        self.updateGeometry()

    def _update_subtitle(self) -> None:
        if self._state == "processing":
            self.subtitle_label.setText("正在处理，请稍候…")
        elif self._state == "result":
            self.subtitle_label.setText("完成 · 可拖拽结果文件")
        elif self._state == "error":
            self.subtitle_label.setText("遇到一点问题")
        elif self._files:
            sheets = sum(max(1, len(b.get("sheets", [])))
                         for b in self._briefs.values())
            self.subtitle_label.setText(
                f"{len(self._files)} 个文件"
                + (f" · {sheets} 张工作表" if self._briefs else ""))
        else:
            self.subtitle_label.setText("拖入表格，即刻整理")
        self._update_count()

    def _update_count(self) -> None:
        self.count_label.setText("双击卡片预览 · 滚轮横向浏览")

    def _update_badge(self) -> None:
        self.tab.set_badge(len(self._files), bool(self._result_path))
        if self._result_path:
            self.footer_status.setText("已完成 · 可直接拖走")
        elif self._files:
            self.footer_status.setText("自动保存到 out_put")
        else:
            self.footer_status.setText(f"v{APP_VERSION}")

    # ================================================================ 文件导入
    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 Excel 文件", "",
            "Excel 文件 (*.xlsx *.xls *.xlsm)")
        if paths:
            self.expand_now()
            self._add_paths(paths)

    def _collect_excel(self, paths: Iterable[str]) -> List[str]:
        try:
            return collect_files(list(paths), recursive=False)
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "收集拖入文件")
            return []

    def _add_paths(self, paths: Iterable[str]) -> None:
        if self._worker is not None:
            return
        valid = self._collect_excel(paths)
        if not valid:
            if not self._files and not self._result_path:
                self._set_state("empty")
            self._flash_footer("没有找到可用的 Excel 文件（xlsx / xls / xlsm）")
            return
        new_paths = [path for path in valid if path not in self._files]
        if not new_paths:
            self._flash_footer("这些文件已经在透镜里了")
            return

        if self._result_path:
            self._clear_result_display()
        had_files = bool(self._files)
        for path in new_paths:
            self._files.append(path)
            card = FileCard(path)
            card.preview_requested.connect(self._preview_file)
            card.remove_requested.connect(self._remove_file)
            self._cards[path] = card
            self.card_strip.add_card(card)
        if had_files:
            QTimer.singleShot(
                30, lambda: self.card_strip.horizontalScrollBar().setValue(
                    self.card_strip.horizontalScrollBar().maximum()))
        self._start_preview_loader(new_paths)
        self._active_action = ""
        for button in self.action_buttons.values():
            button.setChecked(False)
        self._set_state("files")
        self.expand_now()

    def _start_preview_loader(self, paths: List[str]) -> None:
        self._loader_token += 1
        token = self._loader_token
        loader = PreviewLoader(token, paths, self)
        loader.item_ready.connect(self._on_brief_ready)
        loader.batch_finished.connect(self._on_batch_finished)
        loader.finished.connect(lambda item=loader: self._on_loader_done(item))
        loader.start()
        self._loaders.append(loader)

    def _on_loader_done(self, loader: PreviewLoader) -> None:
        if loader in self._loaders:
            self._loaders.remove(loader)
        loader.deleteLater()

    def _on_brief_ready(self, token: int, path: str, payload: object) -> None:
        if token != self._loader_token:
            return
        if not isinstance(payload, dict):
            return
        card = self._cards.get(path)
        if card is None:
            return
        self._briefs[path] = payload
        card.set_brief(payload)
        self._update_subtitle()

    def _on_batch_finished(self, token: int) -> None:
        if token != self._loader_token:
            return
        self._update_subtitle()

    def _remove_file(self, path: str) -> None:
        if self._worker is not None:
            return
        card = self._cards.pop(path, None)
        if card is not None:
            self.card_strip.remove_card(card)
        self._briefs.pop(path, None)
        if path in self._files:
            self._files.remove(path)
        self._update_subtitle()
        self._update_badge()
        if not self._files:
            self._active_action = ""
            for button in self.action_buttons.values():
                button.setChecked(False)
            if self._result_path:
                self._set_state("result")
            else:
                self._set_state("empty")

    def _clear_files(self) -> None:
        if self._worker is not None:
            return
        self._loader_token += 1
        self._files.clear()
        self._briefs.clear()
        self._cards.clear()
        self.card_strip.clear()
        self._active_action = ""
        for button in self.action_buttons.values():
            button.setChecked(False)
        self._clear_result_display()
        self._set_state("empty")
        self._refresh_action_state()
        self._update_badge()
        self._flash_footer("已清空，重新拖入文件即可开始")

    def _preview_file(self, path: str) -> None:
        from app.ui.widgets.preview_dialog import PreviewDialog
        dialog = PreviewDialog(path, self)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        screen = QGuiApplication.screenAt(QCursor.pos()) or self._screen
        if screen is not None:
            available = screen.availableGeometry()
            width = min(960, max(680, available.width() - 80))
            height = min(600, max(440, available.height() - 80))
            dialog.resize(width, height)
            dialog.move(available.center().x() - width // 2,
                        available.center().y() - height // 2)
        dialog.exec_()

    # ================================================================ 拖放
    def _mime_has_supported(self, mime) -> bool:
        if not mime.hasUrls():
            return False
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if os.path.isdir(path):
                return True
            if os.path.splitext(path)[1].lower() in (".xlsx", ".xls", ".xlsm"):
                return True
        return False

    def dragEnterEvent(self, event):  # noqa: N802
        if self._worker is not None or not self._mime_has_supported(event.mimeData()):
            event.ignore()
            return
        self._drag_active = True
        self._collapse_timer.stop()
        self.expand_now()
        if self._state != "empty":
            self.drop_hint.setGeometry(0, 0, self.width(), self.height())
            self.drop_hint.show()
            self.drop_hint.raise_()
            self.drop_hint.start()
        else:
            self.drop_zone.set_active(True)
        event.acceptProposedAction()
        self.update()

    def dragMoveEvent(self, event):  # noqa: N802
        if self._drag_active:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):  # noqa: N802
        self._end_drag_visual()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if not self._drag_active:
            event.ignore()
            return
        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if url.isLocalFile()]
        self._end_drag_visual()
        self._play_drop_pulse()
        self._add_paths(paths)
        event.acceptProposedAction()

    def _end_drag_visual(self) -> None:
        self._drag_active = False
        self.drop_hint.stop()
        self.drop_zone.set_active(False)
        self.update()

    # ================================================================ 标签拖动
    def mousePressEvent(self, event):  # noqa: N802
        if (event.button() == Qt.LeftButton
                and not self._expanded and not self._animating):
            self._tab_drag_active = True
            self._tab_drag_moved = False
            self._tab_drag_origin = QPoint(event.globalPos())
            self._tab_drag_offset = QPoint(event.pos())
            self._expand_timer.stop()
            self._collapse_timer.stop()
            self.setCursor(Qt.ClosedHandCursor)
            QToolTip.hideText()
            self._drag_glass_timer.start()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if not self._tab_drag_active:
            super().mouseMoveEvent(event)
            return
        if not (event.buttons() & Qt.LeftButton):
            self._finish_tab_drag(cancelled=True)
            return
        if (not self._tab_drag_moved
                and (event.globalPos() - self._tab_drag_origin)
                .manhattanLength() < 4):
            return
        self._tab_drag_moved = True
        screen = self._screen_for_point(event.globalPos())
        if screen is not None:
            self._screen = screen
        point = event.globalPos() - self._tab_drag_offset
        anchor = self._clamp_anchor(point)
        if anchor != self._tab_anchor or self.pos() != anchor:
            self._tab_anchor = anchor
            self.move(anchor)
        event.accept()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._tab_drag_active and event.button() == Qt.LeftButton:
            moved = self._finish_tab_drag()
            if not moved:
                self.expand_now()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _finish_tab_drag(self, cancelled: bool = False) -> bool:
        if not self._tab_drag_active:
            return False
        moved = self._tab_drag_moved
        self._tab_drag_active = False
        self._tab_drag_moved = False
        self._drag_glass_timer.stop()
        self.setCursor(Qt.OpenHandCursor
                       if not self._expanded else Qt.ArrowCursor)
        if moved:
            self._tab_anchor = self._clamp_anchor(self.pos())
            self._anchor_changed = True
            self._save_anchor()
            self._suppress_hover = True
            self._refresh_tab_backdrop()
        return moved

    def _drag_zone_rect(self) -> QRect:
        """收起态顶部的拖动区：悬停这里不会触发展开，方便按住移动。"""
        return QRect(self.x(), self.y(), COLLAPSED_W, 54)

    def _refresh_tab_backdrop(self) -> None:
        if self._expanded or self._animating:
            return
        try:
            target = self.geometry()
            self._backdrop.refresh(target, target)
            self._update_backdrop_theme()
            self.update()
        except Exception:  # noqa: BLE001
            pass

    def contextMenuEvent(self, event):  # noqa: N802
        menu = QMenu(self)
        action_expand = menu.addAction("展开透镜")
        action_workbench = menu.addAction("打开高级工作台…")
        menu.addSeparator()
        action_quit = menu.addAction("退出")
        chosen = menu.exec_(event.globalPos())
        if chosen is action_expand:
            self.expand_now()
        elif chosen is action_workbench:
            self.open_workbench()
        elif chosen is action_quit:
            QApplication.quit()

    # ================================================================ 动作
    def _on_action(self, kind: str) -> None:
        if not self._files or self._worker is not None:
            return
        self._active_action = kind
        for name, button in self.action_buttons.items():
            button.setChecked(name == kind)
        self.option_bar.configure(kind)
        self.option_bar.set_busy(False)
        if self._state == "result":
            self._set_state("result")
        else:
            self._set_state("files")
        self._refresh_action_state()
        if self._state != "result":
            self.stack.setCurrentWidget(self.files_page)
        self._update_subtitle()

    def _start_task(self) -> None:
        if self._worker is not None or not self._files:
            return
        action = self._active_action or "merge"
        try:
            ensure_output_dir()
            if action == "merge":
                if self.option_bar.toggle_rename.isChecked():
                    output = unique_path(
                        timestamped_file(OUTPUT_DIR, "合并结果"))
                else:
                    output = os.path.join(OUTPUT_DIR, "合并结果.xlsx")
                func = merge_for_lens
                kwargs = {
                    "output_path": output,
                    "add_source": self.option_bar.toggle_source.isChecked(),
                }
                subtitle = "读取表头 · 对齐列 · 写入结果"
            elif action == "split":
                output = timestamped_dir(OUTPUT_DIR, "拆分结果")
                os.makedirs(output, exist_ok=True)
                func = split_by_sheet
                kwargs = {"output_dir": output}
                subtitle = "逐文件读取 · 每张 Sheet 输出为独立文件"
            else:
                output = timestamped_dir(OUTPUT_DIR, "清洗结果")
                os.makedirs(output, exist_ok=True)
                func = clean_for_lens
                kwargs = {"output_dir": output}
                subtitle = "清理空行空格 · 统一数字与日期格式"
        except OSError as exc:
            record_exception(exc, "准备输出目录")
            self._show_error(explain(exc).to_text())
            return

        self._last_action = action
        self._success_anim.stop()
        self._success_glow = 0.0
        self._clear_result_display()
        for button in self.action_buttons.values():
            button.setChecked(False)
        self._state = "processing"
        self._set_state("processing")
        self._set_bar_visible(self.option_bar, False, EXPANDED_W, 46,
                              animate=False)
        self.processing_view.ring.set_value(0.0, animate=False)
        self.processing_view.ring.set_indeterminate(True)
        names = {"merge": "合并", "split": "拆分", "clean": "清洗"}
        self.processing_view.set_state(
            f"正在{names.get(action, '处理')} {len(self._files)} 个文件…",
            subtitle)
        self.processing_view.cancel.setEnabled(True)
        self._refresh_action_state()
        self._expand_now_if_needed()

        task_args = (list(self._files),)
        worker = TaskWorker(func, task_args, kwargs, self)
        worker.log.connect(self._on_worker_log)
        worker.progress.connect(self._on_worker_progress)
        worker.ok.connect(self._on_worker_ok)
        worker.err.connect(self._on_worker_err)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self._task_output = output
        worker.start()

    def _expand_now_if_needed(self) -> None:
        if not self._expanded:
            self.expand_now()

    def _on_worker_log(self, message: str, level: str) -> None:
        text = str(message or "").strip()
        for prefix in ("✔", "✓", "✗", "⚠", "ℹ", "⏹"):
            text = text.replace(prefix, "").strip()
        if text:
            self.processing_view.set_state(
                self.processing_view.title.text(), text[:72])

    def _on_worker_progress(self, done: int, total: int) -> None:
        if total <= 0:
            return
        value = max(0.0, min(1.0, done / total))
        self.processing_view.ring.set_indeterminate(False)
        self.processing_view.ring.set_value(value)
        action = self._last_action
        names = {"merge": "合并", "split": "拆分", "clean": "清洗"}
        self.processing_view.title.setText(
            f"正在{names.get(action, '处理')} {done}/{total} 个文件…")

    def _on_worker_ok(self, result) -> None:
        action = self._last_action
        output = ""
        if isinstance(result, dict):
            output = str(result.get("output", "") or "")
        if not output:
            output = getattr(self, "_task_output", "")
        if not output or not os.path.exists(output):
            self._show_error(
                "处理结束，但没有找到结果文件",
                "任务没有返回有效的输出路径，或文件在完成后被移动。",
                "请重试，或点「高级处理」在工作台中查看详细日志。")
            return
        self._result_path = output
        self._result_stats = result if isinstance(result, dict) else {}
        self.processing_view.ring.set_indeterminate(False)
        self.processing_view.ring.set_value(1.0)
        if output:
            self.result_card.set_result(output, self._result_stats, action)
        self._state = "result"
        self._active_action = ""
        for button in self.action_buttons.values():
            button.setChecked(False)
        self._set_state("result")
        self._refresh_action_state()
        self._update_badge()
        self._play_success_glow()
        self.result_ready.emit(output)
        self._collapse_timer.stop()
        if not self.frameGeometry().contains(QCursor.pos()):
            self._collapse_timer.start(3200)

    def _on_worker_err(self, message: str) -> None:
        lines = [line.strip() for line in str(message or "").splitlines()
                 if line.strip()]
        title = lines[0] if lines else "处理没有完成"
        detail = ""
        hint = ""
        for line in lines[1:]:
            if line.startswith("原因："):
                detail = line[3:].strip()
            elif line.startswith("建议："):
                hint = line[3:].strip()
            elif not detail:
                detail = line
        self._show_error(title, detail, hint)
        self.error_occurred.emit(title)

    def _on_worker_cancelled(self) -> None:
        self._state = "files" if self._files else "empty"
        self._set_state(self._state)
        self._refresh_action_state()
        self._flash_footer("已停止，当前文件处理完后中断")

    def _on_worker_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._refresh_action_state()
        if self._state == "processing":
            self._state = "files" if self._files else "empty"
            self._set_state(self._state)

    def _cancel_task(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        self.processing_view.cancel.setEnabled(False)
        self.processing_view.set_state(
            self.processing_view.title.text(), "正在停止…当前文件处理完后中断")

    def _retry_task(self) -> None:
        if not self._files or self._worker is not None:
            return
        action = self._last_action or "merge"
        self._active_action = action
        for name, button in self.action_buttons.items():
            button.setChecked(name == action)
        self.option_bar.configure(action)
        self._refresh_action_state()
        self._start_task()

    def _show_error(self, title: str, detail: str = "", hint: str = "") -> None:
        self.error_view.set_error(title, detail, hint)
        self._state = "error"
        self._set_state("error")
        self._set_bar_visible(self.option_bar, False, EXPANDED_W, 46,
                              animate=False)
        self._refresh_action_state()
        self._update_badge()

    def report_global_error(self, text: str) -> None:
        """全局异常兜底：透镜内直接显示友好错误，而不是弹系统对话框。"""
        lines = [line.strip() for line in str(text or "").splitlines()
                 if line.strip()]
        title = lines[0] if lines else "界面操作出错"
        detail = ""
        hint = ""
        for line in lines[1:]:
            if line.startswith("原因："):
                detail = line[3:].strip()
            elif line.startswith("建议："):
                hint = line[3:].strip()
        self.expand_now()
        self._show_error(title, detail, hint)
        self.error_occurred.emit(title)

    # ================================================================ 结果
    def _dismiss_result(self) -> None:
        self._clear_result_display()
        self._state = "files" if self._files else "empty"
        self._set_state(self._state)
        self._refresh_action_state()

    def _clear_result_display(self) -> None:
        self._result_path = ""
        self._result_stats = {}
        self.result_hint.setText("结果已保存到 out_put，可直接拖走或点击打开")

    def _on_result_drag_started(self) -> None:
        self._external_drag = True
        self._collapse_timer.stop()

    def _on_result_drag_finished(self) -> None:
        self._external_drag = False
        if not self.frameGeometry().contains(QCursor.pos()):
            self._collapse_timer.start(1200)

    # ================================================================ 高级工作台
    def open_workbench(self) -> None:
        page_key = self._active_action or self._last_action or "merge"
        if page_key == "clean":
            page_key = "format"
        if page_key not in ("merge", "split", "format"):
            page_key = "merge"
        try:
            from app.ui.main_window import MainWindow
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "打开高级工作台")
            self._show_error("无法打开高级工作台", explain(exc).title)
            return
        if self._workbench is None:
            self._workbench = MainWindow()
            self._workbench.setAttribute(Qt.WA_DeleteOnClose, True)
            self._workbench.destroyed.connect(
                lambda *_: setattr(self, "_workbench", None))
        files = list(self._files)
        try:
            self._workbench.set_initial_batch(files, page_key)
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "同步文件到工作台")
        self._workbench.show()
        self._workbench.raise_()
        self._workbench.activateWindow()
        self.collapse_now()

    # ================================================================ 托盘 / 关闭
    def show_context_menu(self, global_pos: QPoint | None = None) -> None:
        event_pos = global_pos or QCursor.pos()
        menu = QMenu(self)
        menu.addAction("展开透镜", self.expand_now)
        menu.addAction("打开高级工作台…", self.open_workbench)
        menu.addSeparator()
        menu.addAction("退出", QApplication.quit)
        menu.exec_(event_pos)

    def _flash_footer(self, text: str) -> None:
        original = f"v{APP_VERSION}"
        self.footer_status.setText(text)
        QTimer.singleShot(
            2600, lambda: self.footer_status.setText(
                "已完成 · 可直接拖走" if self._result_path
                else ("自动保存到 out_put" if self._files else original)))

    def shutdown(self) -> None:
        self._hover_timer.stop()
        self._expand_timer.stop()
        self._collapse_timer.stop()
        self._drag_glass_timer.stop()
        if self._anchor_changed:
            self._save_anchor()
        self._loader_token += 1
        for loader in list(self._loaders):
            try:
                loader.stop()
                loader.wait(1500)
            except Exception:  # noqa: BLE001
                pass
        self._loaders.clear()
        if self._worker is not None:
            try:
                self._worker.cancel()
                self._worker.wait(2500)
            except Exception:  # noqa: BLE001
                pass
            self._worker = None

    def closeEvent(self, event):  # noqa: N802
        self.shutdown()
        super().closeEvent(event)

