"""批量提取列 / 批量替换内容。"""
import os
import re
from typing import Callable, List, Optional, Sequence, Tuple

import pandas as pd

from .common import noop_log, noop_progress, quote_path, unique_path
from .errors import FriendlyError, explain
from .excel_engine import read_workbook, write_dataframe, write_workbook

_MAP_SEARCH_HEADERS = {
    "查找内容", "查找", "原内容", "原值", "旧内容", "旧值", "search", "from",
}
_MAP_REPLACE_HEADERS = {
    "替换为", "替换", "新内容", "新值", "替换内容", "replace", "to",
}


def _write_result(frames, path):
    if len(frames) == 1:
        sheet_name, frame = next(iter(frames.items()))
        write_dataframe(frame, path, sheet_name=sheet_name)
    else:
        write_workbook(frames, path)


def _map_cell_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _is_replacement_header(row) -> bool:
    first = _map_cell_text(row[0]).strip().lower()
    second = _map_cell_text(row[1]).strip().lower()
    return first in _MAP_SEARCH_HEADERS or second in _MAP_REPLACE_HEADERS


def read_replacement_map(path: str) -> List[Tuple[str, str]]:
    """读取替换对照表（第一张工作表，第一列查找、第二列替换）。

    首行可以是「查找内容 / 替换为」表头；空查找内容的行会被跳过。
    """
    raw = pd.read_excel(path, sheet_name=0, header=None, dtype=str)
    if raw.empty or raw.shape[1] < 2:
        raise FriendlyError(
            "替换对照表格式不正确",
            detail="对照表至少需要两列：第一列为查找内容，第二列为替换为。",
            hint="请把替换规则整理成两列后重新导入。",
        )

    rows = raw.values.tolist()
    if rows and _is_replacement_header(rows[0]):
        rows = rows[1:]

    rules: List[Tuple[str, str]] = []
    for row in rows:
        search = _map_cell_text(row[0])
        replacement = _map_cell_text(row[1])
        if not search:
            continue
        rules.append((search, replacement))

    if not rules:
        raise FriendlyError(
            "对照表中没有可用的替换规则",
            detail="所有行的「查找内容」都是空的。",
            hint="请在对照表第一列填写需要查找的内容后重试。",
        )
    return rules


def extract_columns(files: List[str],
                    columns: Sequence[str],
                    output_dir: str,
                    all_sheets: bool = True,
                    progress: Optional[Callable[[int, int], None]] = None,
                    log: Optional[Callable[[str, str], None]] = None) -> dict:
    """从每个文件中提取指定列并另存。"""
    log = log or noop_log
    progress = progress or noop_progress

    if not columns:
        raise ValueError("请填写需要提取的列名")
    if not files:
        raise ValueError("请先添加 Excel 文件")

    os.makedirs(output_dir, exist_ok=True)
    total = max(len(files), 1)
    count = 0

    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        try:
            workbook = read_workbook(path)
        except Exception as exc:  # noqa: BLE001
            log(f"✗ 读取失败：{name}（{explain(exc).title}）", "error")
            progress(index, total)
            continue

        out_frames = {}
        for sheet_name, frame in workbook.items():
            if not all_sheets and out_frames:
                break
            available = [c for c in columns if c in frame.columns]
            missing = [c for c in columns if c not in frame.columns]
            if missing:
                log(f"⚠ {name} [{sheet_name}] 缺少列：{'、'.join(missing)}", "warn")
            if not available:
                continue
            out_frames[sheet_name] = frame[available].reset_index(drop=True)

        if not out_frames:
            log(f"⚠ {name}：未匹配到任何目标列", "warn")
            progress(index, total)
            continue

        out_path = unique_path(os.path.join(output_dir, f"extracted_{os.path.splitext(name)[0]}.xlsx"))
        _write_result(out_frames, out_path)
        count += 1
        log(f"✓ 已提取：{name} → {quote_path(out_path)}", "success")
        progress(index, total)

    if count == 0:
        raise RuntimeError("没有文件成功提取，请检查列名是否一致。")
    log(f"✔ 提取完成：共输出 {count} 个文件 → {quote_path(output_dir)}", "success")
    return {"files": count, "columns": list(columns), "output": output_dir}


def _build_rules(search: str,
                 replacement: str,
                 replacement_map: Optional[Sequence[Sequence[str]]],
                 regex: bool,
                 case_sensitive: bool):
    """整理并预编译替换规则，提前发现无效正则。"""
    if replacement_map:
        raw_rules = [
            ("" if pattern is None else str(pattern),
             "" if value is None else str(value))
            for pattern, value in replacement_map
        ]
    else:
        if not search:
            raise ValueError("请填写需要查找的内容，或导入替换对照表")
        raw_rules = [(str(search), "" if replacement is None else str(replacement))]

    rules = [(pattern, value) for pattern, value in raw_rules if pattern != ""]
    if not rules:
        raise ValueError("没有可用的替换规则")

    flags = 0 if case_sensitive else re.IGNORECASE
    compiled = []
    for rule_index, (pattern, value) in enumerate(rules, start=1):
        if regex:
            try:
                compiled_pattern = re.compile(pattern, flags)
                # 同时校验替换内容中的 \\1 等分组引用
                compiled_pattern.sub(value, "")
            except re.error as exc:
                raise FriendlyError(
                    "替换规则中的正则表达式无效",
                    detail=f"第 {rule_index} 条规则：{exc}",
                    hint="请检查正则表达式与替换内容，或取消勾选「使用正则表达式」。",
                ) from exc
            compiled.append((compiled_pattern, value, True))
        else:
            compiled.append((pattern, value, False))
    return rules, compiled


def _replace_in_series(series: pd.Series, compiled_rules, case_sensitive: bool) -> pd.Series:
    """依次应用所有规则；未发生替换的单元格保持原值 / 原类型。"""
    def transform(value):
        if value is None:
            return value
        try:
            if pd.isna(value):
                return value
        except (TypeError, ValueError):
            pass

        text = value if isinstance(value, str) else str(value)
        updated = text
        for pattern, replacement, is_regex in compiled_rules:
            if is_regex:
                updated = pattern.sub(replacement, updated)
            elif case_sensitive:
                updated = updated.replace(pattern, replacement)
            else:
                updated = re.sub(
                    re.escape(pattern),
                    lambda _match, text_value=replacement: text_value,
                    updated, flags=re.IGNORECASE)
        return updated if updated != text else value

    return series.map(transform)


def replace_content(files: List[str],
                    search: str,
                    replacement: str,
                    output_dir: str,
                    columns: Optional[Sequence[str]] = None,
                    regex: bool = False,
                    case_sensitive: bool = True,
                    all_sheets: bool = True,
                    replacement_map: Optional[Sequence[Sequence[str]]] = None,
                    progress: Optional[Callable[[int, int], None]] = None,
                    log: Optional[Callable[[str, str], None]] = None) -> dict:
    """批量查找替换单元格内容。

    ``replacement_map`` 为 ``[(查找内容, 替换为), ...]``，会按顺序逐条执行；
    提供对照表时忽略单条 ``search`` / ``replacement``。
    """
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加 Excel 文件")

    rules, compiled_rules = _build_rules(
        search, replacement, replacement_map, regex, case_sensitive)

    os.makedirs(output_dir, exist_ok=True)
    total = max(len(files), 1)
    count = 0
    replaced_total = 0

    if replacement_map:
        log(f"ℹ 已加载 {len(rules)} 条替换规则", "info")

    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        try:
            # dtype=object 保留「00123」等文本编号，避免被 pandas 自动转成数字
            workbook = read_workbook(path, dtype=object)
        except Exception as exc:  # noqa: BLE001
            log(f"✗ 读取失败：{name}（{explain(exc).title}）", "error")
            progress(index, total)
            continue

        out_frames = {}
        file_changed = 0
        for sheet_name, frame in workbook.items():
            if not all_sheets and out_frames:
                break
            frame = frame.copy()
            targets = [c for c in (columns or frame.columns) if c in frame.columns]
            for col in targets:
                original = frame[col].astype(object)
                updated = _replace_in_series(original, compiled_rules, case_sensitive)
                changed = int((original.astype(str) != updated.astype(str)).sum())
                file_changed += changed
                frame[col] = updated
            out_frames[sheet_name] = frame

        replaced_total += file_changed
        out_path = unique_path(os.path.join(output_dir, f"replaced_{os.path.splitext(name)[0]}.xlsx"))
        _write_result(out_frames, out_path)
        count += 1
        log(f"✓ 已替换：{name}（修改 {file_changed} 个单元格）"
            f" → {quote_path(out_path)}", "success")
        progress(index, total)

    rule_note = f"使用 {len(rules)} 条规则，" if replacement_map else ""
    log(f"✔ 替换完成：{rule_note}处理 {count} 个文件，修改 {replaced_total} 个单元格"
        f" → {quote_path(output_dir)}", "success")
    return {
        "files": count,
        "cells": replaced_total,
        "rules": len(rules),
        "output": output_dir,
    }
