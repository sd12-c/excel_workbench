"""透镜界面的视觉常量：颜色、字体、圆角与尺寸。"""
from PyQt5.QtGui import QColor, QFont

# --------------------------------------------------------------------------- #
# 颜色
# --------------------------------------------------------------------------- #
INK = QColor("#172033")
INK_SOFT = QColor("#2f3a52")
MUTED = QColor("#6d7890")
FAINT = QColor("#98a2b6")
ACCENT = QColor("#4f7cff")
ACCENT_DEEP = QColor("#345fe8")
ACCENT_SOFT = QColor("#e8efff")
MINT = QColor("#42cf9f")
SUCCESS = QColor("#2fbf82")
SUCCESS_SOFT = QColor("#e7fbf1")
WARN = QColor("#f0a23a")
DANGER = QColor("#e25563")
GLASS_WHITE = QColor(255, 255, 255, 235)
GLASS_EDGE = QColor(255, 255, 255, 180)

# --------------------------------------------------------------------------- #
# 尺寸
# --------------------------------------------------------------------------- #
COLLAPSED_W = 44
COLLAPSED_H = 154
EXPANDED_W = 616
EXPANDED_H = 500
PANEL_RADIUS = 26
CARD_W = 156
CARD_H = 168
CARD_GAP = 12
ACTION_H = 86


def font(size: int, weight: int = QFont.Normal, spacing: float = 0.0) -> QFont:
    """返回统一字体；spacing 为字间距（px）。"""
    value = QFont("Microsoft YaHei UI")
    value.setPixelSize(int(size))
    value.setWeight(int(weight))
    if spacing:
        value.setLetterSpacing(QFont.AbsoluteSpacing, float(spacing))
    return value
