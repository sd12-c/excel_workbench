"""全局异常兜底：未捕获的异常也转成友好提示写进运行日志面板。"""
import sys
import threading

from app.core.errors import explain, record_exception


def install(window) -> None:
    """安装 sys.excepthook / threading.excepthook。

    这样即使异常发生在 Qt 槽函数或子线程中，运行日志面板收到的也是
    中文提示，而不是控制台里的原始 Traceback。
    """

    def handle(exc: BaseException, context: str) -> None:
        try:
            record_exception(exc, context)
            info = explain(exc)
            panel = getattr(window, "log_panel", None)
            if panel is None:
                return
            panel.append(f"✗ {context}出错：{info.title}", "error")
            if info.detail:
                panel.append(f"    原因：{info.detail}", "error")
            if info.hint:
                panel.append(f"    建议：{info.hint}", "error")
        except Exception:  # noqa: BLE001 - 兜底逻辑本身绝不能再抛出异常
            pass

    def excepthook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        handle(exc_value, "界面操作")

    sys.excepthook = excepthook

    def thread_hook(args) -> None:
        if args.exc_type in (SystemExit, KeyboardInterrupt):
            return
        handle(args.exc_value, "后台线程")

    threading.excepthook = thread_hook
