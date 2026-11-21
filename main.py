"""Excel 批量工作台 - 程序入口。"""
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
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont, QIcon
    from PyQt5.QtWidgets import QApplication, QMessageBox

    from app.config import (APP_ICON_FILE, APP_NAME, APP_VERSION,
                            ensure_runtime_dirs, load_stylesheet)
    from app.core.errors import explain, record_exception
    from app.ui.error_hook import install as install_error_hook
    from app.ui.main_window import MainWindow
except BaseException:  # noqa: BLE001
    _log_startup_failure("导入依赖失败")
    raise


def main() -> int:
    ensure_runtime_dirs()

    # 高 DPI 支持（必须在 QApplication 实例化之前设置）
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setWindowIcon(QIcon(APP_ICON_FILE))
    app.setStyleSheet(load_stylesheet())

    try:
        window = MainWindow()
    except Exception as exc:  # noqa: BLE001
        record_exception(exc, "启动界面")
        QMessageBox.critical(None, "启动失败", explain(exc).to_text())
        return 1

    install_error_hook(window)
    window.show()
    return app.exec_()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BaseException:  # noqa: BLE001
        _log_startup_failure("运行异常")
        raise
