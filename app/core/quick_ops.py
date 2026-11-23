"""透镜快捷操作：把核心能力包装成「一键完成」的轻量任务。

这些函数只做业务编排，不依赖 Qt；界面层通过 TaskWorker 在后台线程调用。
输出默认落在 ``out_put`` 下的时间戳目录 / 文件，避免覆盖用户原文件。
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Callable, List, Optional

from .common import (noop_log, noop_progress, quote_path, safe_sheet_name,
                     sanitize_filename, unique_path)
from .errors import FriendlyError, explain
from .excel_engine import read_workbook, write_dataframe
from .formatter import format_files
from .merger import merge_files

# 一键清洗使用的默认规则：安全、可逆（只另存副本），不删除重复行。
QUICK_CLEAN_RULES = [
    "remove_empty_rows",
    "remove_empty_cols",
    "strip_text",
    "normalize_numbers",
    "normalize_dates",
    "clear_hyperlinks",
    "clear_comments",
]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def timestamped_dir(output_root: str, label: str) -> str:
    """返回 ``<输出根>/<标签>_时间戳`` 目录（不自动创建）。"""
    return os.path.join(output_root, f"{label}_{_stamp()}")


def timestamped_file(output_root: str, label: str) -> str:
    """返回 ``<输出根>/<标签>_时间戳.xlsx``。"""
    return os.path.join(output_root, f"{label}_{_stamp()}.xlsx")


def merge_for_lens(files: List[str],
                   output_path: str,
                   add_source: bool = True,
                   progress: Optional[Callable[[int, int], None]] = None,
                   log: Optional[Callable[[str, str], None]] = None) -> dict:
    """一键合并：所有文件的所有工作表 → 一张总表。"""
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加需要合并的 Excel 文件")

    folder = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(folder, exist_ok=True)

    log(f"开始合并 {len(files)} 个文件…", "info")
    result = merge_files(
        files,
        output_path,
        all_sheets=True,
        add_source=add_source,
        source_column="来源文件",
        sheet_column="来源工作表",
        alignment="union",
        ignore_empty_sheets=True,
        sort_columns="",
        sort_ascending=True,
        progress=progress,
        log=log,
    )
    result = dict(result or {})
    result["output"] = output_path
    return result


def split_by_sheet(files: List[str],
                   output_dir: str,
                   progress: Optional[Callable[[int, int], None]] = None,
                   log: Optional[Callable[[str, str], None]] = None) -> dict:
    """一键拆分：每张工作表 → 一个独立 xlsx 文件。"""
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加需要拆分的 Excel 文件")

    os.makedirs(output_dir, exist_ok=True)
    total = max(len(files), 1)
    files_written = 0
    sheets_written = 0
    failed = 0

    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        stem = os.path.splitext(name)[0]
        try:
            workbook = read_workbook(path)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log(f"✗ 读取失败：{name}（{explain(exc).title}）", "error")
            progress(index, total)
            continue

        kept = 0
        for sheet_name, frame in workbook.items():
            if frame is None:
                continue
            frame = frame.copy()
            frame.columns = [str(column).strip() for column in frame.columns]
            frame = frame.reset_index(drop=True)

            label = safe_sheet_name(sheet_name) or "Sheet1"
            filename_label = sanitize_filename(label)
            candidate = os.path.join(
                output_dir, f"{stem}_{filename_label}.xlsx")
            out_path = unique_path(candidate)
            write_dataframe(frame, out_path, sheet_name=label)
            kept += 1
            files_written += 1
            sheets_written += 1

        if kept:
            log(f"✓ {name}：拆出 {kept} 个工作表", "success")
        else:
            log(f"⚠ {name}：没有可拆分的工作表", "warn")
        progress(index, total)

    if files_written == 0:
        raise FriendlyError(
            "没有可拆分的工作表",
            detail="所有文件都没有成功读取到工作表，或工作表内容为空。",
            hint="请确认文件没有被占用、格式正确，然后重新拖入。",
        )

    log(f"✔ 拆分完成：共生成 {files_written} 个文件 → {quote_path(output_dir)}",
        "success")
    return {
        "files": files_written,
        "sheets": sheets_written,
        "failed": failed,
        "output": output_dir,
    }


def clean_for_lens(files: List[str],
                   output_dir: str,
                   progress: Optional[Callable[[int, int], None]] = None,
                   log: Optional[Callable[[str, str], None]] = None) -> dict:
    """一键清洗：空行空列、首尾空格、数字/日期统一、清理链接与批注。"""
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加需要清洗的 Excel 文件")

    os.makedirs(output_dir, exist_ok=True)
    stats = format_files(
        files,
        output_dir,
        global_rules=QUICK_CLEAN_RULES,
        recognize_chinese_dates=True,
        date_format="%Y-%m-%d",
        all_sheets=True,
        progress=progress,
        log=log,
    )
    result = dict(stats or {})
    result["output"] = output_dir
    result.setdefault("files", 0)
    return result
