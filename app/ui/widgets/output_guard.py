"""输出文件前置检测：文件已存在 / 被占用时自动避让或询问用户。"""
import os
from typing import Callable, Optional

from PyQt5.QtWidgets import QMessageBox

from app.core.common import quote_path
from app.core.output_safety import build_renamed_path, is_file_locked


def resolve_output_file(parent,
                        path: str,
                        *,
                        auto_rename: bool,
                        log: Callable[[str, str], None]) -> Optional[str]:
    """任务开始前检查输出文件，返回最终使用的路径；用户取消时返回 None。

    - 路径不存在：直接使用；
    - 已存在且勾选“自动重命名”：自动加时间戳 / 序号；
    - 已存在且被其他软件打开、未勾选自动重命名：弹窗询问；
    - 已存在但未被占用、未勾选自动重命名：保持原来的覆盖行为。
    """
    if not os.path.exists(path):
        return path
    if os.path.isdir(path):
        # 目录路径交给核心层提示“目标是文件夹”，不在这里改名
        return path

    name = os.path.basename(path)
    locked = is_file_locked(path)

    if auto_rename:
        new_path = build_renamed_path(path)
        reason = "正在被其他软件打开" if locked else "已存在"
        log(f"⚠ 目标文件{reason}，已自动改名保存为：{quote_path(new_path)}", "warn")
        return new_path

    if not locked:
        return path

    if not _ask_auto_rename(parent, name):
        log("✗ 已停止：目标文件正在被其他软件打开，请关闭后重试，"
            "或勾选「目标文件已存在时自动重命名」。", "warn")
        return None

    new_path = build_renamed_path(path)
    log(f"⚠ 目标文件被占用，已自动改名保存为：{quote_path(new_path)}", "warn")
    return new_path


def _ask_auto_rename(parent, filename: str) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle("目标文件被占用")
    box.setIcon(QMessageBox.Question)
    box.setText(f"目标文件「{filename}」正在被其他软件打开。")
    box.setInformativeText("是否自动生成新文件名保存？")
    yes_button = box.addButton("是，自动重命名", QMessageBox.YesRole)
    box.addButton("否，停止任务", QMessageBox.NoRole)
    box.setDefaultButton(yes_button)
    box.exec_()
    return box.clickedButton() is yes_button
