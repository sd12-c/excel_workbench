"""Excel 工作台 - 程序入口。

默认只显示桌面上的悬浮透镜（可拖动并记住位置）；高级参数界面在需要时再从透镜打开。
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback


def _log_startup_failure(context: str = "启动失败") -> str:
    """把打包后启动阶段的异常写入文件，方便定位问题。"""
    text = f"[{context}]\n{traceback.format_exc()}\n"
    candidates = []
    try:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        candidates.append(os.path.join(base, "startup_error.log"))
    except Exception:  # noqa: BLE001
        pass
    candidates.append(os.path.join(
        tempfile.gettempdir(), "ExcelWorkbench_startup_error.log"))
    for path in candidates:
        try:
            with open(path, "a", encoding="utf-8") as fp:
                fp.write(text)
            return path
        except OSError:
            continue
    return ""


try:
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtGui import QFont, QIcon
    from PyQt5.QtWidgets import (QApplication, QMenu, QMessageBox,
                                 QSystemTrayIcon)

    from app.config import (APP_ICON_FILE, APP_NAME, APP_VERSION,
                            ensure_runtime_dirs, load_stylesheet)
    from app.core.errors import explain, record_exception
    from app.ui.error_hook import install as install_error_hook
    from app.ui.lens.lens_window import LensWindow
except BaseException:  # noqa: BLE001
    _log_startup_failure("导入依赖失败")
    raise


def _build_tray(app, lens) -> QSystemTrayIcon | None:
    """托盘图标：透镜没有任务栏入口，用它兜底展开 / 退出。"""
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(QIcon(APP_ICON_FILE), app)
    tray.setToolTip(f"{APP_NAME} · 悬停标签展开，按住顶部可拖动")
    menu = QMenu()
    action_expand = menu.addAction("展开透镜")
    action_expand.triggered.connect(lens.expand_now)
    action_workbench = menu.addAction("打开高级工作台…")
    action_workbench.triggered.connect(lens.open_workbench)
    menu.addSeparator()
    action_quit = menu.addAction("退出")
    action_quit.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray._menu = menu  # 保持引用，避免被 GC
    tray.activated.connect(
        lambda reason: lens.expand_now()
        if reason == QSystemTrayIcon.DoubleClick else None)
    tray.show()
    lens._tray = tray
    return tray


def main() -> int:
    ensure_runtime_dirs()

    # 高 DPI 支持（必须在 QApplication 实例化之前设置）
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # QtWebEngine（流水线画布）要求共享 OpenGL 上下文；必须在 QApplication 之前设置。
    if hasattr(Qt, "AA_ShareOpenGLContexts"):
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setWindowIcon(QIcon(APP_ICON_FILE))
    app.setStyleSheet(load_stylesheet())
    app.setQuitOnLastWindowClosed(False)

    try:
        lens = LensWindow()
    except Exception as exc:  # noqa: BLE001
        record_exception(exc, "启动悬浮透镜")
        info = explain(exc)
        # 透镜异常时退回原来的完整工作台，至少不耽误用户处理表格
        try:
            from app.ui.main_window import MainWindow
            window = MainWindow()
            install_error_hook(window)
            QMessageBox.warning(
                None, "已切换为完整工作台",
                "悬浮透镜没有成功启动，已为你打开完整工作台。\n\n"
                f"{info.to_text()}")
            app.setQuitOnLastWindowClosed(True)
            window.show()
            return app.exec_()
        except Exception:  # noqa: BLE001
            QMessageBox.critical(None, "启动失败", info.to_text())
            return 1

    install_error_hook(lens)
    tray = _build_tray(app, lens)

    def notify_result(path: str) -> None:
        if tray is None or not path:
            return
        try:
            if lens._expanded:
                return
            tray.showMessage(
                "Excel 处理完成",
                f"{os.path.basename(path)}\n悬停透镜查看，或直接把结果拖到文件夹 / 微信 / WPS。",
                QSystemTrayIcon.Information, 4200)
        except Exception:  # noqa: BLE001
            pass

    lens.result_ready.connect(notify_result)
    app.aboutToQuit.connect(lens.shutdown)

    lens.show()
    if "--workbench" in sys.argv:
        QTimer.singleShot(0, lens.open_workbench)
    return app.exec_()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:  # noqa: BLE001
        _log_startup_failure("运行异常")
        raise
