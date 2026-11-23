"""主窗口：侧边栏 + 页面栈 + 日志面板。"""
import os
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAction, QFileDialog, QHBoxLayout, QLabel,
                             QMainWindow, QPushButton, QSplitter,
                             QStackedWidget, QVBoxLayout, QWidget)

from app.config import APP_VERSION, SCHEME_FILE
from app.core.common import quote_path
from app.core.errors import FriendlyError, explain, record_exception
from app.ui.pages import (AboutPage, ConvertPage, ExtractPage, FormatPage,
                          MergePage, PipelinePage, PivotPage, SplitPage,
                          TemplatePage)
from app.ui.scheme import SCHEMA_VERSION, load_scheme_file, save_scheme_file
from app.ui.widgets.backdrop import SoftBackdrop
from app.ui.widgets.log_panel import LogPanel
from app.ui.widgets.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Excel 工作台 · 高级参数  v{APP_VERSION}")
        self.resize(1280, 840)
        self.setMinimumSize(1080, 720)
        self._busy_pages = set()
        self._scheme_path = SCHEME_FILE
        self._build_ui()
        self._connect_signals()
        self._switch_page(0)
        self._load_startup_scheme()

    # ------------------------------------------------------------ 布局
    def _build_ui(self) -> None:
        self._build_menu()

        central = SoftBackdrop()
        central.setObjectName("Root")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()
        root.addWidget(self.sidebar)

        content = QWidget()
        content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 18, 22, 18)
        content_layout.setSpacing(14)

        # 顶部标题
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = QLabel("")
        self.title_label.setObjectName("PageTitle")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("PageSubtitle")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)

        header_layout.addLayout(title_box)

        header_layout.addStretch(1)

        self.mode_badge = QLabel("悬浮透镜 · 高级参数")
        self.mode_badge.setObjectName("ModeBadge")
        self.mode_badge.setToolTip(
            "这里是可以精细调整参数的高级工作台；回到桌面右侧的悬浮透镜可继续拖拽处理")
        header_layout.addWidget(self.mode_badge, 0, Qt.AlignVCenter)

        self.btn_save_scheme = QPushButton("保存方案")
        self.btn_save_scheme.setObjectName("GhostButton")
        self.btn_save_scheme.setCursor(Qt.PointingHandCursor)
        self.btn_save_scheme.setToolTip(
            "保存各页面的输出路径与参数到项目 config 文件夹（不含源文件列表）")
        self.btn_save_scheme.clicked.connect(self._save_scheme)
        self.btn_load_scheme = QPushButton("加载方案…")
        self.btn_load_scheme.setObjectName("GhostButton")
        self.btn_load_scheme.setCursor(Qt.PointingHandCursor)
        self.btn_load_scheme.setToolTip("从 JSON 方案文件恢复各页面选项")
        self.btn_load_scheme.clicked.connect(self._load_scheme)
        header_layout.addWidget(self.btn_save_scheme)
        header_layout.addWidget(self.btn_load_scheme)

        content_layout.addWidget(header)

        # 主区域分割：页面 + 日志
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)

        self.stack = QStackedWidget()
        self.pages = [PipelinePage(), MergePage(), SplitPage(), FormatPage(),
                      ExtractPage(), TemplatePage(), PivotPage(), ConvertPage(),
                      AboutPage()]
        for page in self.pages:
            self.stack.addWidget(page)
        self.splitter.addWidget(self.stack)

        self.log_panel = LogPanel()
        self.splitter.addWidget(self.log_panel)

        self.splitter.setStretchFactor(0, 8)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([620, 150])
        content_layout.addWidget(self.splitter, 1)

        root.addWidget(content, 1)

    def _build_menu(self) -> None:
        """顶部方案 / 帮助菜单。"""
        self.menuBar().setNativeMenuBar(False)

        scheme_menu = self.menuBar().addMenu("方案(&S)")
        scheme_menu.setToolTipsVisible(True)
        save_action = QAction("保存当前方案", self)
        save_action.setShortcut("Ctrl+S")
        save_action.setToolTip(
            "保存各页面的输出路径与参数到项目 config 文件夹（不含源文件列表）")
        save_action.triggered.connect(self._save_scheme)
        scheme_menu.addAction(save_action)

        save_as_action = QAction("方案另存为…", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._save_scheme_as)
        scheme_menu.addAction(save_as_action)

        load_action = QAction("加载方案…", self)
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._load_scheme)
        scheme_menu.addAction(load_action)

        help_menu = self.menuBar().addMenu("帮助(&H)")
        about_action = QAction("关于 Excel 批量工作台", self)
        about_action.setShortcut("F1")
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        badge = getattr(self, "mode_badge", None)
        if badge is not None:
            badge.setVisible(self.width() >= 1180)

    def closeEvent(self, event):  # noqa: N802
        for page in self.pages:
            shutdown = getattr(page, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:  # noqa: BLE001
                    pass
        super().closeEvent(event)

    # ------------------------------------------------------------ 从透镜进入
    def set_initial_batch(self, files, page_key: str = "merge") -> None:
        """由悬浮透镜的「高级」入口调用：切到对应页面并带入文件。"""
        mapping = {
            "pipeline": "pipeline",
            "merge": "merge",
            "split": "split",
            "format": "format",
            "clean": "format",
            "extract": "extract",
            "template": "template",
            "pivot": "pivot",
            "convert": "convert",
        }
        target_key = mapping.get(str(page_key or ""), "merge")
        target_index = 0
        for index, page in enumerate(self.pages):
            if getattr(page, "SCHEME_KEY", "") == target_key:
                target_index = index
                break
        page = self.pages[target_index]
        file_list = getattr(page, "file_list", None)
        if file_list is not None and files:
            file_list.add_paths(list(files))
        self._switch_page(target_index)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------ 信号
    def _connect_signals(self) -> None:
        self.sidebar.page_changed.connect(self._switch_page)
        for page in self.pages:
            page.log_message.connect(self.log_panel.append)
            page.progress_changed.connect(self.log_panel.set_progress)
            page.busy_changed.connect(
                lambda busy, target=page: self._on_busy(target, busy))
        self.log_panel.stop_requested.connect(self._stop_tasks)

    def _switch_page(self, index: int) -> None:
        if not (0 <= index < len(self.pages)):
            return
        page = self.pages[index]
        self.stack.setCurrentIndex(index)
        self.title_label.setText(page.PAGE_TITLE)
        self.subtitle_label.setText(page.PAGE_SUBTITLE)
        self.sidebar.set_current(index)

        # 流水线画布内部自带运行日志抽屉，给画布留出完整高度；
        # 切回其他页面时恢复工作台底部的统一日志面板。
        is_pipeline = getattr(page, "SCHEME_KEY", "") == "pipeline"
        self.log_panel.setVisible(not is_pipeline)
        if is_pipeline:
            self.splitter.setSizes([1, 0])
        else:
            self.splitter.setSizes([620, 150])

    def _on_busy(self, page, busy: bool) -> None:
        if busy:
            self._busy_pages.add(page)
        else:
            self._busy_pages.discard(page)

        any_busy = bool(self._busy_pages)
        self.log_panel.set_busy(any_busy)
        if not any_busy:
            self.log_panel.reset_progress()

    def _stop_tasks(self) -> None:
        stopped = False
        for page in self.pages:
            if page.stop_task():
                stopped = True
        if stopped:
            self.log_panel.set_stopping()

    # ------------------------------------------------------------ 方案保存 / 加载
    def _collect_scheme(self) -> dict:
        pages = {}
        for page in self.pages:
            key = getattr(page, "SCHEME_KEY", "")
            if not key:
                continue
            pages[key] = page.to_scheme()
        active_page = self.stack.currentIndex()
        if active_page >= len(self.pages) - 1:
            active_page = 0
        active_page_key = getattr(self.pages[active_page], "SCHEME_KEY", "")
        return {
            "schema": SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "active_page": active_page,
            "active_page_key": active_page_key,
            "pages": pages,
        }

    def _apply_scheme(self, data: dict) -> None:
        pages = data.get("pages", {})
        if not isinstance(pages, dict):
            raise FriendlyError(
                "方案文件格式不正确",
                detail="方案文件中的 pages 字段必须是对象。",
                hint="请重新保存方案，或选择其他方案文件。",
            )
        for page in self.pages:
            key = getattr(page, "SCHEME_KEY", "")
            if not key:
                continue
            payload = pages.get(key)
            if isinstance(payload, dict):
                page.apply_scheme(payload)

        # 优先按页面 key 恢复，避免新增页面后旧的 active_page 索引错位。
        active_key = data.get("active_page_key")
        if isinstance(active_key, str) and active_key:
            for index, page in enumerate(self.pages):
                if getattr(page, "SCHEME_KEY", "") == active_key:
                    self._switch_page(index)
                    return
        active_page = data.get("active_page")
        if (isinstance(active_page, int)
                and not isinstance(active_page, bool)
                and 0 <= active_page < len(self.pages) - 1):
            self._switch_page(active_page)

    def _save_scheme(self) -> None:
        path = self._scheme_path or SCHEME_FILE
        if not self._save_scheme_to(path):
            return
        if os.path.abspath(path) != os.path.abspath(SCHEME_FILE):
            try:
                save_scheme_file(SCHEME_FILE, self._collect_scheme())
            except Exception as exc:  # noqa: BLE001
                self._report_scheme_error(exc, "设置默认方案")
                return
            self.log_panel.append("ℹ 已更新下次启动自动加载的方案", "info")

    def _save_scheme_to(self, path: str) -> bool:
        try:
            data = self._collect_scheme()
            save_scheme_file(path, data)
        except Exception as exc:  # noqa: BLE001
            self._report_scheme_error(exc, "保存方案")
            return False
        self._scheme_path = path
        self.log_panel.append(f"✔ 方案已保存：{quote_path(path)}", "success")
        return True

    def _save_scheme_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "方案另存为", self._scheme_path or SCHEME_FILE,
            "方案文件 (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            data = self._collect_scheme()
            save_scheme_file(path, data)
        except Exception as exc:  # noqa: BLE001
            self._report_scheme_error(exc, "保存方案")
            return

        self._scheme_path = path
        self.log_panel.append(f"✔ 方案已保存：{quote_path(path)}", "success")
        if os.path.abspath(path) != os.path.abspath(SCHEME_FILE):
            try:
                save_scheme_file(SCHEME_FILE, data)
            except Exception as exc:  # noqa: BLE001
                self._report_scheme_error(exc, "设置默认方案")
                return
            self.log_panel.append("ℹ 已设为下次启动自动加载的方案", "info")

    def _load_scheme(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "加载方案", self._scheme_path or SCHEME_FILE,
            "方案文件 (*.json)")
        if not path:
            return

        try:
            data = load_scheme_file(path)
            self._apply_scheme(data)
        except Exception as exc:  # noqa: BLE001
            self._report_scheme_error(exc, "加载方案")
            return

        self._scheme_path = path
        self.log_panel.append(f"✔ 方案已加载：{quote_path(path)}", "success")
        if os.path.abspath(path) != os.path.abspath(SCHEME_FILE):
            try:
                save_scheme_file(SCHEME_FILE, data)
            except Exception as exc:  # noqa: BLE001
                self._report_scheme_error(exc, "设置默认方案")
                return
            self.log_panel.append("ℹ 已设为下次启动自动加载的方案", "info")

    def _load_startup_scheme(self) -> None:
        self._scheme_path = SCHEME_FILE
        if not os.path.exists(SCHEME_FILE):
            return
        try:
            data = load_scheme_file(SCHEME_FILE)
            self._apply_scheme(data)
        except Exception as exc:  # noqa: BLE001
            self._report_scheme_error(exc, "自动加载方案")
            return
        self.log_panel.append(
            f"✔ 已自动加载上次方案：{quote_path(SCHEME_FILE)}", "info")

    def _report_scheme_error(self, exc: BaseException, action: str) -> None:
        record_exception(exc, action)
        info = explain(exc)
        self.log_panel.append(f"✗ {action}失败：{info.title}", "error")
        if info.detail:
            self.log_panel.append(f"    原因：{info.detail}", "error")
        if info.hint:
            self.log_panel.append(f"    建议：{info.hint}", "error")

    def _show_about(self, _checked: bool = False) -> None:
        self._switch_page(len(self.pages) - 1)