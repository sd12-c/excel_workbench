"""流水线画布页面：QWebEngineView + QWebChannel + 文件拖拽。

前端是构建好的 React Flow 静态页（app/resources/pipeline），这里只负责：

- 给 WebView 注入 Python 桥；
- 接收画布拖入的 Excel 路径，读取表头预览；
- 把整张流程图 JSON 交给后台线程执行；
- 把节点进度 / 日志 / 结果实时推回前端。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, List, Optional

from PyQt5.QtCore import QObject, QProcess, Qt, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QApplication, QFileDialog, QLabel, QStackedWidget,
                             QVBoxLayout, QWidget)

try:
    from PyQt5.QtWebChannel import QWebChannel
    from PyQt5.QtWebEngineWidgets import (QWebEngineProfile,
                                          QWebEngineSettings, QWebEngineView)
    WEBENGINE_AVAILABLE = True
    WEBENGINE_IMPORT_ERROR = ""
except Exception as _webengine_exc:  # noqa: BLE001
    # 没装 PyQtWebEngine 时不要拖垮整个工作台：只让流水线页显示安装提示。
    QWebChannel = None
    QWebEngineProfile = None
    QWebEngineSettings = None
    QWebEngineView = None
    WEBENGINE_AVAILABLE = False
    WEBENGINE_IMPORT_ERROR = str(_webengine_exc)

from app.config import (APP_VERSION, OUTPUT_DIR, PIPELINE_HTML,
                        PIPELINE_WEBENGINE_DIR, ensure_output_dir)
from app.core.common import normalize_path
from app.core.errors import explain, friendly_text, record_exception
from app.core.excel_engine import collect_files
from app.core.pipeline import parse_graph, validate_for_run
from app.core.pipeline_templates import (delete_user_template,
                                         get_last_load_error, list_templates,
                                         save_user_template)
from app.ui.lens.loader import PreviewLoader
from app.workers.pipeline_worker import PipelineWorker

from .base_page import BasePage

MAX_CANVAS_FILES = 80


class PipelineBridge(QObject):
    """暴露给 JS 的 QWebChannel 对象（名字固定为 bridge）。"""

    event = pyqtSignal(str)

    def __init__(self, page: "PipelinePage", parent=None):
        super().__init__(parent)
        self._page = page

    @pyqtSlot()
    def ready(self) -> None:
        self._page.on_bridge_ready()

    @pyqtSlot(str)
    def runPipeline(self, payload: str) -> None:  # noqa: N802
        self._page.start_pipeline(payload)

    @pyqtSlot()
    def stopPipeline(self) -> None:  # noqa: N802
        self._page.stop_pipeline()

    @pyqtSlot()
    def getTemplates(self) -> None:  # noqa: N802
        self._page.send_templates()

    @pyqtSlot(str)
    def saveTemplate(self, payload: str) -> None:  # noqa: N802
        self._page.save_template(payload)

    @pyqtSlot(str)
    def deleteTemplate(self, template_id: str) -> None:  # noqa: N802
        self._page.delete_template(template_id)

    @pyqtSlot(str)
    def pickFiles(self, node_id: str) -> None:  # noqa: N802
        self._page.pick_files(node_id)

    @pyqtSlot(str)
    def requestPreviews(self, payload: str) -> None:  # noqa: N802
        self._page.request_previews(payload)

    @pyqtSlot(str, str)
    def pickOutputDir(self, request_id: str, current: str) -> None:  # noqa: N802
        self._page.pick_output_dir(request_id, current)

    @pyqtSlot(str)
    def openPreview(self, path: str) -> None:  # noqa: N802
        self._page.open_preview(path)

    @pyqtSlot(str)
    def openPath(self, path: str) -> None:  # noqa: N802
        self._page.open_path(path)

    @pyqtSlot(str, str)
    def logFromJs(self, message: str, level: str) -> None:  # noqa: N802
        self._page.log_from_js(message, level)


_WebViewBase = QWebEngineView if WEBENGINE_AVAILABLE else QWidget


class PipelineWebView(_WebViewBase):
    """拦截系统文件拖拽，把路径和落点交给 Python。"""

    files_dropped = pyqtSignal(list, int, int)
    drag_active = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drag_active.emit(True)
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):  # noqa: N802
        self.drag_active.emit(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):  # noqa: N802
        if event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls()
                     if url.isLocalFile()]
            self.drag_active.emit(False)
            event.acceptProposedAction()
            if paths:
                self.files_dropped.emit(paths, event.pos().x(), event.pos().y())
            return
        super().dropEvent(event)


class PipelinePage(BasePage):
    PAGE_TITLE = "流水线画布"
    PAGE_SUBTITLE = "把 Excel 拖进画布，用节点连线编排合并 / 清洗 / 拆分 / 输出，实时查看每个节点的处理数量"
    SCHEME_KEY = "pipeline"

    def __init__(self, parent=None):
        self._worker: Optional[PipelineWorker] = None
        self._bridge: Optional[PipelineBridge] = None
        self._channel: Optional[QWebChannel] = None
        self._view: Optional[PipelineWebView] = None
        self._preview_loaders: List[PreviewLoader] = []
        self._preview_token = 0
        self._last_dir = ""
        self._ready = False
        self._shutdown = False
        super().__init__(parent)

    # ------------------------------------------------------------ 界面
    def build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        self._fallback = QLabel(self)
        self._fallback.setObjectName("PipelineFallback")
        self._fallback.setAlignment(Qt.AlignCenter)
        self._fallback.setWordWrap(True)
        self._stack.addWidget(self._fallback)
        layout.addWidget(self._stack, 1)

        if not WEBENGINE_AVAILABLE:
            self._show_fallback(
                "流水线画布需要 PyQtWebEngine，但当前环境没有安装或加载失败。\n\n"
                "请在项目目录执行：\n"
                "pip install PyQtWebEngine\n\n"
                "安装完成后重新打开工作台即可。\n\n"
                f"技术信息：{WEBENGINE_IMPORT_ERROR or '未知错误'}")
            return

        if not os.path.exists(PIPELINE_HTML):
            self._show_fallback(
                "流水线画布资源还没有构建。\n\n"
                "开发环境请先在 pipeline 目录运行：\n"
                "npm install && npm run build\n\n"
                f"静态页面应位于：\n{PIPELINE_HTML}")
            return

        self._configure_webengine()
        self._view = PipelineWebView(self)
        self._stack.addWidget(self._view)
        self._stack.setCurrentWidget(self._view)
        self._setup_view()
        self._view.load(QUrl.fromLocalFile(PIPELINE_HTML))

        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def _configure_webengine(self) -> None:
        """把缓存放到 config 目录，绿色版不污染系统 AppData。"""
        try:
            storage = os.path.join(PIPELINE_WEBENGINE_DIR, "storage")
            cache = os.path.join(PIPELINE_WEBENGINE_DIR, "cache")
            os.makedirs(storage, exist_ok=True)
            os.makedirs(cache, exist_ok=True)
            profile = QWebEngineProfile.defaultProfile()
            profile.setPersistentStoragePath(storage)
            profile.setCachePath(cache)
            profile.setHttpCacheType(QWebEngineProfile.NoCache)
            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "配置流水线 WebEngine 缓存")

    def _setup_view(self) -> None:
        # 避免右键菜单里的「重新加载」误触后丢失未保存的画布
        self._view.setContextMenuPolicy(Qt.NoContextMenu)
        settings = self._view.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, False)

        self._channel = QWebChannel(self)
        self._bridge = PipelineBridge(self, self)
        self._channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(self._channel)

        self._view.files_dropped.connect(self._on_files_dropped)
        self._view.drag_active.connect(self._on_drag_active)
        self._view.loadFinished.connect(self._on_load_finished)
        self._view.renderProcessTerminated.connect(self._on_render_terminated)

    def _show_fallback(self, text: str) -> None:
        self._fallback.setText(text)
        self._stack.setCurrentWidget(self._fallback)

    # ------------------------------------------------------------ 页面生命周期
    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            self._show_fallback(
                "流水线画布加载失败。\n\n"
                "请确认程序目录完整（app/resources/pipeline 未被删除），"
                "或重新安装 / 重新构建前端资源。")
            self.log_message.emit("✗ 流水线画布加载失败", "error")
            return
        self.log_message.emit("ℹ 流水线画布已加载", "info")

    def _on_render_terminated(self, status, exit_code: int) -> None:
        record_exception(
            RuntimeError(f"QtWebEngine 渲染进程退出：status={status}, code={exit_code}"),
            "流水线画布渲染进程")
        self.log_message.emit(
            f"✗ 流水线画布渲染进程异常退出（{exit_code}），请重新打开工作台", "error")

    def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1500)
        for loader in list(self._preview_loaders):
            try:
                loader.stop()
                loader.wait(800)
            except Exception:  # noqa: BLE001
                pass
        self._preview_loaders.clear()
        if self._view is not None:
            try:
                self._view.page().setWebChannel(None)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------ JS 事件
    def _send_event(self, name: str, payload: Optional[Dict[str, Any]] = None) -> None:
        if self._bridge is None:
            return
        try:
            text = json.dumps(
                {"type": str(name), "payload": payload or {}},
                ensure_ascii=False)
        except (TypeError, ValueError):
            text = json.dumps({
                "type": str(name),
                "payload": {"message": "事件数据无法序列化"},
            }, ensure_ascii=False)
        self._bridge.event.emit(text)

    def _run_js(self, script: str) -> None:
        if self._view is None:
            return
        try:
            self._view.page().runJavaScript(script)
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "执行画布脚本")

    def _toast(self, message: str, level: str = "info") -> None:
        self._send_event("toast", {"message": str(message), "level": str(level)})

    def _default_output_dir(self) -> str:
        try:
            return ensure_output_dir()
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "准备流水线输出目录")
            return OUTPUT_DIR

    def on_bridge_ready(self) -> None:
        self._ready = True
        output_dir = self._default_output_dir()
        try:
            templates = list_templates()
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "读取流水线模板")
            templates = []
            self.log_message.emit("⚠ 读取流水线模板失败，已只显示内置模板", "warn")
        load_error = get_last_load_error()
        if load_error:
            self.log_message.emit(f"⚠ {load_error}", "warn")
        self._send_event("ready", {
            "appVersion": APP_VERSION,
            "outputDir": output_dir,
            "templates": templates,
            "defaultTemplateId": "builtin_merge",
            "maxFiles": MAX_CANVAS_FILES,
        })

    # ------------------------------------------------------------ 文件拖入
    def _on_drag_active(self, active: bool) -> None:
        self._run_js(
            "window.pipelineApp && window.pipelineApp.setDragActive("
            + ("true" if active else "false") + ");")

    def _on_files_dropped(self, paths: list, x: int, y: int) -> None:
        self.add_files(paths, x, y)

    def pick_files(self, node_id: str = "") -> None:
        start_dir = self._last_dir or os.path.expanduser("~")
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择 Excel 文件", start_dir,
            "Excel 文件 (*.xlsx *.xls *.xlsm)")
        if not paths:
            return
        self._last_dir = os.path.dirname(paths[0])
        self.add_files(paths, None, None, node_id=node_id)

    def add_files(self, paths: Iterable[str], x: Optional[int] = None,
                  y: Optional[int] = None, node_id: str = "") -> None:
        """展开文件夹、过滤格式，然后发给画布并开始读取表头预览。"""
        raw_paths = [str(item) for item in paths if str(item).strip()]
        try:
            files = collect_files(raw_paths, recursive=False)
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "读取拖入的文件")
            self._toast("读取拖入的文件失败，请检查文件是否可访问", "error")
            return
        if not files:
            self._toast("只支持 .xlsx / .xls / .xlsm 文件（文件夹会读取其中一层 Excel）",
                        "warn")
            self.log_message.emit("⚠ 没有可添加的 Excel 文件", "warn")
            return
        if len(files) > MAX_CANVAS_FILES:
            self._toast(f"一次最多添加 {MAX_CANVAS_FILES} 个文件，已保留前 {MAX_CANVAS_FILES} 个",
                        "warn")
            files = files[:MAX_CANVAS_FILES]

        normalized: List[str] = []
        for path in files:
            clean = normalize_path(path)
            if clean and clean not in normalized:
                normalized.append(clean)

        files_json = json.dumps(normalized, ensure_ascii=True)
        node_json = json.dumps(str(node_id or ""), ensure_ascii=True)
        x_json = "null" if x is None else str(int(x))
        y_json = "null" if y is None else str(int(y))
        # 预览由 JS 在节点建立后通过 requestPreviews() 主动请求，避免
        # 「预览事件先于 addFiles 到达」时找不到对应节点。
        self._run_js(
            "window.pipelineApp && window.pipelineApp.addFiles("
            f"{files_json}, {x_json}, {y_json}, {node_json});")
        self.log_message.emit(f"ℹ 已添加 {len(normalized)} 个文件到画布", "info")

    def request_previews(self, payload: str) -> None:
        """JS 建好文件节点后请求读取表头预览。"""
        try:
            paths = json.loads(payload or "[]")
        except (TypeError, ValueError):
            return
        if not isinstance(paths, list):
            return
        clean = [normalize_path(str(item)) for item in paths if str(item).strip()]
        clean = [item for item in clean if item]
        if clean:
            self._request_previews(clean)

    def _request_previews(self, paths: List[str]) -> None:
        if not paths:
            return
        self._preview_token += 1
        loader = PreviewLoader(self._preview_token, paths, self)
        loader.item_ready.connect(self._on_preview_ready)
        loader.batch_finished.connect(
            lambda token, worker=loader: self._on_preview_finished(token, worker))
        self._preview_loaders.append(loader)
        loader.start()

    def _on_preview_ready(self, _token: int, path: str, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        self._send_event("file-preview", {
            "path": path,
            "columns": list(payload.get("columns") or []),
            "rows": [list(row) for row in (payload.get("rows") or [])],
            "sheets": list(payload.get("sheets") or []),
            "error": str(payload.get("error") or ""),
        })

    def _on_preview_finished(self, _token: int, loader: PreviewLoader) -> None:
        try:
            if loader in self._preview_loaders:
                self._preview_loaders.remove(loader)
            loader.deleteLater()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 模板
    def send_templates(self) -> None:
        load_error = get_last_load_error()
        if load_error:
            self.log_message.emit(f"⚠ {load_error}", "warn")
        try:
            templates = list_templates()
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "读取流水线模板")
            templates = []
        self._send_event("templates", {"templates": templates})

    def save_template(self, payload: str) -> None:
        try:
            data = json.loads(payload or "{}")
            if not isinstance(data, dict):
                raise ValueError("模板数据格式不正确")
            record = save_user_template(
                data.get("name", ""),
                data.get("graph") or {},
                data.get("description", ""))
        except Exception as exc:  # noqa: BLE001
            info = explain(exc)
            self.log_message.emit(f"✗ 保存模板失败：{info.title}", "error")
            if info.detail:
                self.log_message.emit(f"    原因：{info.detail}", "error")
            self._toast(f"保存模板失败：{info.title}", "error")
            return

        self.log_message.emit(f"✔ 已保存流水线模板：{record.get('name', '')}", "success")
        try:
            templates = list_templates()
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "刷新流水线模板")
            templates = []
        self._send_event("templates", {"templates": templates})
        self._send_event("template-saved", record)
        self._toast(f"模板「{record.get('name', '')}」已保存", "success")

    def delete_template(self, template_id: str) -> None:
        try:
            removed = delete_user_template(template_id)
        except Exception as exc:  # noqa: BLE001
            info = explain(exc)
            self.log_message.emit(f"✗ 删除模板失败：{info.title}", "error")
            self._toast(f"删除模板失败：{info.title}", "error")
            return
        if not removed:
            self._toast("没有找到这个模板，可能已被删除", "warn")
            return
        self.log_message.emit("✔ 已删除流水线模板", "info")
        try:
            templates = list_templates()
        except Exception as exc:  # noqa: BLE001
            record_exception(exc, "刷新流水线模板")
            templates = []
        self._send_event("templates", {"templates": templates})
        self._toast("模板已删除", "success")

    def pick_output_dir(self, request_id: str, current: str) -> None:
        start = current or self._default_output_dir()
        path = QFileDialog.getExistingDirectory(
            self, "选择输出文件夹", start, QFileDialog.ShowDirsOnly)
        self._send_event("output-dir-picked", {
            "requestId": str(request_id or ""),
            "path": normalize_path(path) if path else "",
        })

    # ------------------------------------------------------------ 运行
    def start_pipeline(self, payload: str) -> None:
        if self.is_busy:
            self._send_event("run-error", {"message": "已有任务正在运行，请稍候……"})
            self._toast("已有任务正在运行", "warn")
            return
        try:
            graph = json.loads(payload or "{}")
            if not isinstance(graph, dict):
                raise ValueError("流程图必须是 JSON 对象")
            parsed = parse_graph(graph)
            validate_for_run(parsed)
        except Exception as exc:  # noqa: BLE001
            info = explain(exc)
            self.log_message.emit(f"✗ 无法运行：{info.title}", "error")
            if info.detail:
                self.log_message.emit(f"    原因：{info.detail}", "error")
            if info.hint:
                self.log_message.emit(f"    建议：{info.hint}", "error")
            self._send_event("run-error", {
                "message": info.title,
                "detail": info.detail,
                "hint": info.hint,
            })
            return

        worker = PipelineWorker(graph, self._default_output_dir(), self)
        worker.event.connect(self._bridge.event.emit)
        worker.log.connect(self.log_message)
        worker.progress.connect(self.progress_changed)
        worker.ok.connect(self._on_pipeline_ok)
        worker.err.connect(self._on_pipeline_err)
        worker.cancelled.connect(self._on_pipeline_cancelled)
        worker.finished.connect(self._on_pipeline_finished)
        self._worker = worker
        self.busy_changed.emit(True)
        self.log_message.emit("▶ 流水线任务已启动", "info")
        worker.start()

    def stop_pipeline(self) -> None:
        if self._worker is None or not self._worker.isRunning():
            return
        self._worker.cancel()
        self.log_message.emit("正在停止流水线……（当前文件处理完成后停止）", "warn")
        self._send_event("run-stopping", {"message": "正在停止……"})
        self._toast("正在停止……", "warn")

    def stop_task(self) -> bool:
        if self._worker is None or not self._worker.isRunning():
            return False
        self.stop_pipeline()
        return True

    def _on_pipeline_ok(self, result: object) -> None:
        if isinstance(result, dict):
            self.log_message.emit(
                f"✔ {result.get('summary', '流水线运行完成')}", "success")

    def _on_pipeline_err(self, message: str) -> None:
        lines = [line.strip() for line in str(message or "").splitlines()
                 if line.strip()]
        if not lines:
            lines = ["流水线运行失败"]
        self.log_message.emit(f"✗ {lines[0]}", "error")
        for line in lines[1:]:
            self.log_message.emit(f"    {line}", "error")

    def _on_pipeline_cancelled(self) -> None:
        self.log_message.emit("⏹ 流水线任务已停止", "warn")

    def _on_pipeline_finished(self) -> None:
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self.busy_changed.emit(False)

    # ------------------------------------------------------------ 打开文件
    def open_preview(self, path: str) -> None:
        target = normalize_path(path)
        if not target or not os.path.exists(target):
            self._toast("找不到要预览的文件", "warn")
            return
        try:
            from app.ui.widgets.preview_dialog import PreviewDialog
            PreviewDialog(target, self.window()).exec_()
        except Exception as exc:  # noqa: BLE001
            info = explain(exc)
            self.log_message.emit(f"✗ 预览失败：{info.title}", "error")
            self._toast(f"预览失败：{info.title}", "error")

    def open_path(self, path: str) -> None:
        target = normalize_path(path)
        if not target or not os.path.exists(target):
            self._toast("文件或文件夹不存在，可能已被移动", "warn")
            return
        try:
            if os.name == "nt" and os.path.isfile(target):
                QProcess.startDetached(
                    "explorer.exe", [f"/select,{os.path.normpath(target)}"])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(target))
        except Exception as exc:  # noqa: BLE001
            info = explain(exc)
            self.log_message.emit(f"✗ 打开位置失败：{info.title}", "error")
            self._toast(f"打开位置失败：{info.title}", "error")

    def log_from_js(self, message: str, level: str = "info") -> None:
        text = str(message or "").strip()
        if text:
            self.log_message.emit(text, str(level or "info"))

    # ------------------------------------------------------------ 方案
    def to_scheme(self) -> dict:
        return {}

    def apply_scheme(self, data: dict) -> None:
        return
