"""毛玻璃背景：采样桌面并柔化，随壁纸颜色轻微混色。

实现要点：

* 展开瞬间抓取面板背后的桌面区域（此时透镜还只是右侧窄条，
  被抓到的窄条会用相邻像素覆盖，再整体强模糊，肉眼不可见）；
* 用大半径盒式模糊 + 提亮 / 轻微增加饱和度，得到磨砂玻璃质感；
* 叠加白色半透明渐变、蓝绿色柔光、细颗粒噪点与高光边框；
* 屏幕抓取失败（远程桌面 / 离屏测试）时自动退回内置柔和渐变。
"""
from __future__ import annotations

import random

from PyQt5.QtCore import QPointF, QRect, QRectF, Qt
from PyQt5.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient,
                         QPainter, QPainterPath, QPixmap, QRadialGradient)

try:  # numpy 随 pandas 一起安装；缺失时退回纯 Qt 缩放模糊
    import numpy as np
except Exception:  # noqa: BLE001
    np = None


def _rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


class GlassBackdrop:
    """缓存一块模糊后的桌面背景。"""

    def __init__(self) -> None:
        self._image = QImage()
        self._average = QColor(226, 232, 244)
        self._noise = self._build_noise()
        self._source = "fallback"

    # ------------------------------------------------------------------ API
    @property
    def available(self) -> bool:
        return not self._image.isNull()

    @property
    def average_color(self) -> QColor:
        return QColor(self._average)

    def set_image(self, image: QImage) -> None:
        """测试或外部注入背景图。"""
        if image is None or image.isNull():
            return
        self._image = image.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self._average = self._calc_average(self._image)
        self._source = "custom"

    def refresh(self, target: QRect, exclude: QRect | None = None) -> None:
        """抓取 target（全局坐标）背后的桌面，模糊后缓存。

        会额外向外多抓一圈（margin），这样即使 target 正好是悬浮标签本身，
        也能用标签周围的桌面像素把标签区域补掉，拖动时玻璃不会出现空洞。
        """
        if target.width() <= 0 or target.height() <= 0:
            return
        screen = QGuiApplication.screenAt(target.center()) \
            or QGuiApplication.primaryScreen()
        if screen is None:
            return

        margin = 56
        capture = target.adjusted(-margin, -margin, margin, margin)
        capture = capture.intersected(screen.availableGeometry())
        if (capture.width() < target.width()
                or capture.height() < target.height()
                or not capture.contains(target)):
            capture = target

        image = self._grab_screen(capture)
        if image is None or image.isNull():
            self._image = self._fallback_image(target.width(), target.height())
            self._average = self._calc_average(self._image)
            self._source = "fallback"
            return

        if exclude is not None and exclude.intersects(capture):
            self._patch_excluded(image, capture, exclude)

        blurred = self._blur(image)
        crop_rect = target.translated(-capture.left(), -capture.top())
        cropped = blurred.copy(crop_rect)
        if cropped.isNull():
            cropped = blurred.scaled(target.width(), target.height(),
                                     Qt.IgnoreAspectRatio,
                                     Qt.SmoothTransformation)
        self._image = cropped
        self._average = self._calc_average(cropped)
        self._source = "desktop"

    def paint(self, painter: QPainter, rect: QRectF, radius: float,
              strength: float = 1.0,
              tint: QColor | None = None,
              dark: bool = False) -> None:
        """把毛玻璃背景画进 rect。strength 0~1 控制壁纸可见度。"""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = _rounded_path(rect, radius)
        painter.setClipPath(path)
        strength = max(0.0, min(strength, 1.0))

        # 1. 壁纸模糊层
        if not self._image.isNull():
            painter.setOpacity(0.50 + 0.18 * strength)
            painter.drawImage(rect, self._image)
            painter.setOpacity(1.0)
        else:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, QColor("#eef2fb"))
            gradient.setColorAt(0.55, QColor("#e3e9f7"))
            gradient.setColorAt(1.0, QColor("#dfe8f5"))
            painter.fillPath(path, gradient)

        if dark:
            # 深色壁纸下的收起态：深色玻璃，真正做到“贴边隐形”
            glass = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            glass.setColorAt(0.0, QColor(28, 35, 52, 168))
            glass.setColorAt(0.45, QColor(20, 26, 40, 152))
            glass.setColorAt(1.0, QColor(14, 19, 30, 170))
            painter.fillPath(path, glass)
            average = QColor(self._average)
            average.setAlpha(26)
            painter.fillPath(path, average)
            painter.setOpacity(0.03)
            painter.drawTiledPixmap(rect.toRect(), self._noise)
            painter.setOpacity(1.0)
            highlight = QLinearGradient(rect.topLeft(),
                                        QPointF(rect.left(), rect.top() + 26))
            highlight.setColorAt(0.0, QColor(255, 255, 255, 46))
            highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillPath(path, highlight)
            painter.restore()

            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QColor(255, 255, 255, 58))
            painter.drawPath(_rounded_path(
                rect.adjusted(0.7, 0.7, -0.7, -0.7), radius - 0.7))
            painter.setPen(QColor(0, 0, 0, 46))
            painter.drawPath(_rounded_path(
                rect.adjusted(0.1, 0.1, -0.1, -0.1), radius - 0.1))
            painter.restore()
            return

        # 2. 半透明白色玻璃层（顶部更亮；收起态更通透）
        base = int(122 + 74 * strength)
        glass = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        glass.setColorAt(0.0, QColor(255, 255, 255, base + 20))
        glass.setColorAt(0.42, QColor(250, 252, 255, base - 8))
        glass.setColorAt(1.0, QColor(244, 248, 255, base + 10))
        painter.fillPath(path, glass)

        # 3. 壁纸平均色轻微混色
        average = QColor(self._average)
        average.setAlpha(20)
        painter.fillPath(path, average)

        # 4. 蓝 / 绿色柔光，模拟环境光反射
        glow = QRadialGradient(QPointF(rect.left() + rect.width() * 0.16,
                                       rect.top() + rect.height() * 0.02),
                               rect.width() * 0.72)
        glow.setColorAt(0.0, QColor(116, 158, 255, 46))
        glow.setColorAt(0.55, QColor(116, 158, 255, 10))
        glow.setColorAt(1.0, QColor(116, 158, 255, 0))
        painter.fillPath(path, glow)

        glow2 = QRadialGradient(QPointF(rect.right() - rect.width() * 0.1,
                                        rect.bottom() + rect.height() * 0.05),
                                rect.width() * 0.55)
        glow2.setColorAt(0.0, QColor(94, 220, 178, 38))
        glow2.setColorAt(1.0, QColor(94, 220, 178, 0))
        painter.fillPath(path, glow2)

        if tint is not None and tint.alpha() > 0:
            painter.fillPath(path, tint)

        # 5. 细微颗粒，避免大面积渐变出现色带
        painter.setOpacity(0.045)
        painter.drawTiledPixmap(rect.toRect(), self._noise)
        painter.setOpacity(1.0)

        # 6. 顶部高光与内侧投影
        highlight = QLinearGradient(rect.topLeft(),
                                    QPointF(rect.left(), rect.top() + 26))
        highlight.setColorAt(0.0, QColor(255, 255, 255, 150))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, highlight)

        inner = QLinearGradient(QPointF(rect.left(), rect.bottom() - 34),
                                QPointF(rect.left(), rect.bottom()))
        inner.setColorAt(0.0, QColor(64, 82, 120, 0))
        inner.setColorAt(1.0, QColor(64, 82, 120, 22))
        painter.fillPath(path, inner)

        painter.restore()

        # 7. 边框
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        edge = _rounded_path(rect.adjusted(0.7, 0.7, -0.7, -0.7), radius - 0.7)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(255, 255, 255,
                              int(118 + 67 * strength)))
        painter.drawPath(edge)
        outer = _rounded_path(rect.adjusted(0.1, 0.1, -0.1, -0.1), radius - 0.1)
        painter.setPen(QColor(47, 60, 92, 30))
        painter.drawPath(outer)
        painter.restore()

    # ------------------------------------------------------------- 内部实现
    def _grab_screen(self, target: QRect) -> QImage | None:
        screen = QGuiApplication.screenAt(target.center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return None
        origin = screen.geometry().topLeft()
        attempts = [(target.x(), target.y())]
        if origin.x() or origin.y():
            attempts.append((target.x() - origin.x(),
                             target.y() - origin.y()))
        pixmap = None
        for x, y in attempts:
            try:
                candidate = screen.grabWindow(
                    0, x, y, target.width(), target.height())
            except Exception:  # noqa: BLE001
                candidate = None
            if candidate is None or candidate.isNull():
                continue
            # 某些多屏坐标实现会返回被裁切的图像，尺寸明显不足时尝试下一种坐标系
            if (candidate.width() < target.width() * 0.9
                    or candidate.height() < target.height() * 0.9):
                continue
            pixmap = candidate
            break
        if pixmap is None or pixmap.isNull():
            return None
        image = pixmap.toImage()
        if image.isNull():
            return None
        if image.width() != target.width() or image.height() != target.height():
            image = image.scaled(target.width(), target.height(),
                                 Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return image.convertToFormat(QImage.Format_RGB32)

    def _patch_excluded(self, image: QImage, target: QRect,
                        exclude: QRect) -> None:
        """把当前透镜窗口占据的区域，用相邻像素覆盖后再模糊。"""
        local = exclude.translated(-target.left(), -target.top())
        local = local.intersected(QRect(0, 0, image.width(), image.height()))
        if local.width() <= 0 or local.height() <= 0:
            return

        width = local.width()
        left_x = local.left() - width
        right_x = local.right() + 1
        if left_x >= 0:
            source_x = left_x
        elif right_x + width <= image.width():
            source_x = right_x
        else:
            # 极端窄屏：复制最近的 1px 并拉伸，模糊后几乎不可见
            source_x = max(0, min(local.left(), image.width() - 1))
            width = max(1, min(width, image.width() - source_x))
        strip = image.copy(source_x, local.top(),
                           max(1, min(width, image.width() - source_x)),
                           local.height())
        if strip.isNull():
            return
        if strip.width() != local.width():
            strip = strip.scaled(local.width(), local.height(),
                                 Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        painter = QPainter(image)
        painter.drawImage(local.topLeft(), strip)
        painter.end()

    def _blur(self, image: QImage) -> QImage:
        if np is not None:
            try:
                return self._numpy_blur(image)
            except Exception:  # noqa: BLE001
                pass
        return self._qt_blur(image)

    def _qt_blur(self, image: QImage) -> QImage:
        width = max(1, image.width())
        height = max(1, image.height())
        small = image.scaled(max(8, width // 22), max(8, height // 22),
                             Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        small = small.scaled(max(16, width // 9), max(16, height // 9),
                             Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return small.scaled(width, height, Qt.IgnoreAspectRatio,
                            Qt.SmoothTransformation)

    def _numpy_blur(self, image: QImage) -> QImage:
        width, height = image.width(), image.height()
        raw = image.convertToFormat(QImage.Format_RGB888)
        buffer = raw.bits()
        buffer.setsize(raw.byteCount())
        array = np.frombuffer(bytes(buffer), dtype=np.uint8).reshape(
            height, raw.bytesPerLine() // 3, 3)[:, :width, :].astype(np.float32)

        radius = max(4, min(width, height) // 38)
        for _ in range(2):
            array = self._box_axis(array, radius, 0)
            array = self._box_axis(array, radius, 1)

        # 提亮 + 轻微提高饱和度，让玻璃更通透
        array = array * 1.045 + 7.0
        gray = array.mean(axis=2, keepdims=True)
        array = gray + (array - gray) * 1.10
        array = np.clip(array, 0, 255).astype(np.uint8)
        array = np.ascontiguousarray(array)

        result = QImage(array.data, width, height, width * 3,
                        QImage.Format_RGB888).copy()
        return result

    @staticmethod
    def _box_axis(array, radius: int, axis: int):
        if radius <= 0:
            return array
        pads = [(0, 0), (0, 0), (0, 0)]
        pads[axis] = (radius, radius)
        padded = np.pad(array, pads, mode="edge")
        cumulative = np.cumsum(padded, axis=axis, dtype=np.float32)
        zeros_shape = list(cumulative.shape)
        zeros_shape[axis] = 1
        cumulative = np.concatenate(
            [np.zeros(zeros_shape, dtype=np.float32), cumulative], axis=axis)

        window = radius * 2 + 1
        high = [slice(None)] * 3
        low = [slice(None)] * 3
        high[axis] = slice(window, None)
        low[axis] = slice(0, -window)
        return (cumulative[tuple(high)] - cumulative[tuple(low)]) / window

    @staticmethod
    def _calc_average(image: QImage) -> QColor:
        sample = image.scaled(1, 1, Qt.IgnoreAspectRatio,
                              Qt.SmoothTransformation)
        return sample.pixelColor(0, 0)

    def _fallback_image(self, width: int, height: int) -> QImage:
        image = QImage(max(width, 10), max(height, 10),
                       QImage.Format_RGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        gradient = QLinearGradient(0, 0, width, height)
        gradient.setColorAt(0.0, QColor("#dbe7fb"))
        gradient.setColorAt(0.45, QColor("#eef1fb"))
        gradient.setColorAt(1.0, QColor("#d7ece8"))
        painter.fillRect(image.rect(), gradient)

        blobs = (
            (QPointF(width * 0.16, height * 0.15), width * 0.55,
             QColor(120, 156, 255, 90)),
            (QPointF(width * 0.82, height * 0.78), width * 0.6,
             QColor(87, 216, 178, 80)),
            (QPointF(width * 0.8, height * 0.12), width * 0.4,
             QColor(255, 186, 146, 55)),
        )
        for center, radius, color in blobs:
            radial = QRadialGradient(center, radius)
            radial.setColorAt(0.0, color)
            radial.setColorAt(1.0, QColor(color.red(), color.green(),
                                          color.blue(), 0))
            painter.fillRect(image.rect(), radial)
        painter.end()
        return image

    def _build_noise(self) -> QPixmap:
        size = 120
        image = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        rng = random.Random(20261123)
        for y in range(size):
            for x in range(size):
                value = rng.randint(0, 255)
                alpha = rng.randint(4, 16)
                image.setPixelColor(x, y, QColor(value, value, value, alpha))
        return QPixmap.fromImage(image)
