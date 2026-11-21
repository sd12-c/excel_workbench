"""按列分组拆分。"""
import os
import re
from typing import Callable, List, Optional

import pandas as pd

from .common import (noop_log, noop_progress, quote_path, safe_sheet_name,
                     sanitize_filename, unique_path)
from .errors import FriendlyError, explain
from .excel_engine import read_workbook, write_dataframe, write_workbook

DEFAULT_FILENAME_TEMPLATE = "{原文件名}_{分组列值}.xlsx"
_SUPPORTED_PLACEHOLDERS = {"分组列值", "原文件名", "工作表名"}
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_RENDER_RE = re.compile(r"\{(分组列值|原文件名|工作表名)\}")


def validate_filename_template(template: str) -> str:
    """校验并规范化文件名模板，返回补全 ``.xlsx`` 后的模板。"""
    text = str(template or "").strip()
    if not text:
        raise ValueError("请填写文件名模板")
    if "{分组列值}" not in text:
        raise ValueError("文件名模板必须包含 {分组列值}")

    unknown = [match.group(0) for match in _PLACEHOLDER_RE.finditer(text)
               if match.group(1) not in _SUPPORTED_PLACEHOLDERS]
    if unknown:
        names = "、".join(dict.fromkeys(unknown))
        raise ValueError(
            f"文件名模板包含不支持的占位符：{names}"
            "（可用：{分组列值}、{原文件名}、{工作表名}）")

    if not text.lower().endswith(".xlsx"):
        text += ".xlsx"
    return text


def _label_of(value) -> str:
    if value is None:
        return "空值"
    try:
        if pd.isna(value):
            return "空值"
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return "空值"
    return str(value)


def _is_empty_key(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def _render_filename(template: str,
                     label: str,
                     source_stem: str,
                     sheet_name: str) -> str:
    values = {
        "分组列值": label,
        "原文件名": source_stem,
        "工作表名": sheet_name,
    }
    return _RENDER_RE.sub(lambda match: values[match.group(1)], template)


def _append_sheet_suffix(filename: str, sheet_name: str) -> str:
    base, extension = os.path.splitext(filename)
    return f"{base}_{sheet_name}{extension or '.xlsx'}"


def split_by_column(files: List[str],
                    column: str,
                    output_dir: str,
                    mode: str = "file",
                    all_sheets: bool = True,
                    skip_empty_groups: bool = False,
                    filename_template: str = DEFAULT_FILENAME_TEMPLATE,
                    progress: Optional[Callable[[int, int], None]] = None,
                    log: Optional[Callable[[str, str], None]] = None) -> dict:
    """按指定列分组拆分 Excel。

    mode = "file"  → 每个分组输出一个独立 Excel 文件
    mode = "sheet" → 每个源工作簿输出一个文件，每个分组一个工作表

    ``filename_template`` 支持 ``{分组列值}`` / ``{原文件名}`` / ``{工作表名}``；
    多工作表拆分时，若模板未包含 ``{工作表名}``，会自动在文件名后追加工作表名。
    """
    log = log or noop_log
    progress = progress or noop_progress

    if not column:
        raise ValueError("请指定用于拆分的列名")
    if not files:
        raise ValueError("请先添加需要拆分的 Excel 文件")

    if mode == "file":
        filename_template = validate_filename_template(filename_template)

    os.makedirs(output_dir, exist_ok=True)
    total = max(len(files), 1)
    groups_written = 0
    files_written = 0
    skipped_groups = 0

    for index, path in enumerate(files, start=1):
        stem = os.path.splitext(os.path.basename(path))[0]
        try:
            workbook = read_workbook(path)
        except Exception as exc:  # noqa: BLE001
            log(f"✗ 读取失败：{os.path.basename(path)}（{explain(exc).title}）", "error")
            progress(index, total)
            continue

        multi_sheet = all_sheets and len(workbook) > 1
        skipped_here = 0

        if mode == "sheet":
            sheet_frames = {}
            for sheet_name, frame in workbook.items():
                if column not in frame.columns:
                    log(f"⚠ [{sheet_name}] 缺少列 “{column}”，已跳过", "warn")
                    continue
                for key, group in frame.groupby(column, dropna=False, sort=True):
                    if group.empty or (skip_empty_groups and _is_empty_key(key)):
                        skipped_here += 1
                        continue
                    label = _label_of(key)
                    target = safe_sheet_name(f"{sheet_name}_{label}")
                    base, seq = target, 1
                    while target in sheet_frames:
                        target = safe_sheet_name(f"{base[:28]}_{seq}")
                        seq += 1
                    sheet_frames[target] = group.reset_index(drop=True)
            if sheet_frames:
                out_path = unique_path(os.path.join(output_dir, f"{stem}_拆分.xlsx"))
                write_workbook(sheet_frames, out_path)
                files_written += 1
                groups_written += len(sheet_frames)
                skipped_note = f"，跳过空分组 {skipped_here} 个" if skipped_here else ""
                log(f"✓ {stem}：拆出 {len(sheet_frames)} 个分组{skipped_note}"
                    f" → {quote_path(out_path)}", "success")
            else:
                skipped_note = f"，跳过空分组 {skipped_here} 个" if skipped_here else ""
                log(f"⚠ {stem}：没有可用分组{skipped_note}", "warn")
        else:
            written = 0
            for sheet_name, frame in workbook.items():
                if column not in frame.columns:
                    log(f"⚠ {os.path.basename(path)} [{sheet_name}] 缺少列 “{column}”，已跳过", "warn")
                    continue
                for key, group in frame.groupby(column, dropna=False, sort=True):
                    if group.empty or (skip_empty_groups and _is_empty_key(key)):
                        skipped_here += 1
                        continue
                    label = sanitize_filename(_label_of(key))
                    filename = _render_filename(
                        filename_template, label, stem, str(sheet_name))
                    if multi_sheet and "{工作表名}" not in filename_template:
                        filename = _append_sheet_suffix(filename, str(sheet_name))
                    filename = sanitize_filename(filename)
                    if not filename.lower().endswith(".xlsx"):
                        filename += ".xlsx"
                    out_path = unique_path(os.path.join(output_dir, filename))
                    write_dataframe(group.reset_index(drop=True), out_path, sheet_name="Sheet1")
                    written += 1
            if written:
                files_written += written
                groups_written += written
                skipped_note = f"，跳过空分组 {skipped_here} 个" if skipped_here else ""
                log(f"✓ {stem}：拆出 {written} 个文件{skipped_note}"
                    f" → {quote_path(output_dir)}", "success")
            elif skipped_here:
                log(f"⚠ {stem}：没有可用分组（已跳过 {skipped_here} 个空分组）", "warn")

        skipped_groups += skipped_here
        progress(index, total)

    if skipped_groups:
        log(f"ℹ 已过滤 {skipped_groups} 个空分组，未生成对应文件", "info")

    if groups_written == 0:
        if skipped_groups:
            raise FriendlyError(
                "没有可拆分的分组",
                detail=f"已跳过 {skipped_groups} 个空分组。",
                hint="请检查分组列是否有值，或取消勾选「过滤空分组」后重试。",
            )
        raise RuntimeError(f"未找到任何可用分组，请确认列名 “{column}” 是否存在。")

    log(f"✔ 拆分完成：共生成 {files_written} 个文件 / {groups_written} 个分组"
        f" → {quote_path(output_dir)}", "success")
    return {
        "files": files_written,
        "groups": groups_written,
        "skipped": skipped_groups,
        "output": output_dir,
    }
