"""模板填充：一份数据源 + 一份 xlsx 模板，按数据行批量生成独立报表。"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from openpyxl import load_workbook

from .common import (noop_log, noop_progress, quote_path, sanitize_filename,
                     unique_path)
from .errors import FriendlyError, explain
from .excel_engine import read_csv_smart, read_workbook

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
_SPECIAL_VALUES = {"序号", "模板名", "数据文件名"}


def _template_error(message: str, detail: str = "", hint: str = "") -> FriendlyError:
    return FriendlyError(message, detail=detail, hint=hint)


def _validate_template(path: str) -> None:
    if not path:
        raise _template_error("请选择 Excel 模板文件")
    if os.path.splitext(path)[1].lower() not in {".xlsx"}:
        raise _template_error(
            "模板必须是 .xlsx 文件",
            detail=f"当前文件：{os.path.basename(path)}",
            hint="请用 Excel 另存为 .xlsx 后再试；.xlsm 宏模板暂不支持。",
        )
    if not os.path.exists(path):
        raise _template_error("找不到模板文件", detail=path)


def _open_template(path: str):
    try:
        return load_workbook(path, data_only=False, read_only=False)
    except Exception as exc:  # noqa: BLE001
        raise _template_error(
            "无法读取 Excel 模板",
            detail=explain(exc).title,
            hint="请确认模板没有被占用、格式正确，并且是 .xlsx 文件。",
        ) from exc


def scan_template_markers(path: str) -> List[str]:
    """扫描模板所有工作表中的 ``{{标记}}``，保持首次出现顺序。"""
    _validate_template(path)
    workbook = _open_template(path)
    markers: List[str] = []
    try:
        for worksheet in workbook.worksheets:
            for row in worksheet.iter_rows():
                for cell in row:
                    value = cell.value
                    if not isinstance(value, str) or "{{" not in value:
                        continue
                    for marker in _PLACEHOLDER_RE.findall(value):
                        marker = marker.strip()
                        if marker and marker not in markers:
                            markers.append(marker)
    finally:
        workbook.close()
    return markers


def _read_data_source(path: str) -> Tuple[pd.DataFrame, str]:
    if not path:
        raise _template_error("请选择 Excel 数据源")
    if not os.path.exists(path):
        raise _template_error("找不到数据源文件", detail=path)

    extension = os.path.splitext(path)[1].lower()
    sheet_name = "CSV"
    try:
        if extension == ".csv":
            frame = read_csv_smart(path).astype(object)
        elif extension in {".xlsx", ".xls", ".xlsm"}:
            workbook = read_workbook(path, dtype=object)
            if not workbook:
                raise _template_error(
                    "数据源里没有工作表",
                    hint="请用 Excel 打开数据源，确认至少有一张工作表。")
            sheet_name, frame = next(iter(workbook.items()))
            sheet_name = str(sheet_name)
        else:
            raise _template_error(
                "不支持的数据源格式",
                detail=f"当前文件：{os.path.basename(path)}",
                hint="支持 .xlsx、.xls、.xlsm 和 .csv。",
            )
    except FriendlyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _template_error(
            "无法读取数据源",
            detail=explain(exc).title,
            hint="请确认文件没有被占用，且内容格式正确。",
        ) from exc

    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.dropna(how="all").reset_index(drop=True)
    return frame, sheet_name


def read_data_columns(path: str) -> Tuple[List[str], str]:
    """给界面用：读取数据源列名和第一个工作表名。"""
    frame, sheet_name = _read_data_source(path)
    return list(frame.columns), sheet_name


def _clean_value(value: Any) -> Any:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    return value


def _text_value(value: Any) -> str:
    value = _clean_value(value)
    if value == "":
        return ""
    if isinstance(value, datetime):
        if (value.hour, value.minute, value.second) == (0, 0, 0):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _row_values(row: pd.Series,
                index: int,
                template_stem: str,
                data_stem: str) -> Dict[str, Any]:
    values = {str(column).strip(): value for column, value in row.items()}
    values.update({
        "序号": index,
        "模板名": template_stem,
        "数据文件名": data_stem,
    })
    return values


def _replace_cell(cell, values: Dict[str, Any]) -> bool:
    text = cell.value
    if not isinstance(text, str) or "{{" not in text:
        return False

    matches = list(_PLACEHOLDER_RE.finditer(text))
    if not matches:
        return False

    # 整个单元格只有一个标记时保留原始数据类型（金额/日期等）。
    if (len(matches) == 1
            and matches[0].start() == 0
            and matches[0].end() == len(text)):
        marker = matches[0].group(1).strip()
        cell.value = _clean_value(values.get(marker, ""))
        return True

    def replace(match):
        marker = match.group(1).strip()
        return _text_value(values.get(marker, ""))

    cell.value = _PLACEHOLDER_RE.sub(replace, text)
    return True


def _fill_one(template_path: str,
              output_path: str,
              values: Dict[str, Any]) -> None:
    workbook = _open_template(template_path)
    try:
        for worksheet in workbook.worksheets:
            for row in worksheet.iter_rows():
                for cell in row:
                    _replace_cell(cell, values)
        workbook.save(output_path)
    finally:
        workbook.close()


def _render_filename(template: str,
                     values: Dict[str, Any],
                     fallback: str) -> str:
    text = str(template or "").strip() or "报表_{{序号}}.xlsx"

    def replace(match):
        marker = match.group(1).strip()
        return _text_value(values.get(marker, ""))

    rendered = _PLACEHOLDER_RE.sub(replace, text).strip()
    if not rendered:
        rendered = fallback
    rendered = sanitize_filename(rendered)
    if not rendered.lower().endswith(".xlsx"):
        rendered += ".xlsx"
    return rendered


def fill_template_reports(data_path: str,
                          template_path: str,
                          output_dir: str,
                          filename_template: str = "报表_{{序号}}.xlsx",
                          skip_empty_rows: bool = True,
                          progress: Optional[Callable[[int, int], None]] = None,
                          log: Optional[Callable[[str, str], None]] = None) -> dict:
    """按数据行循环填充模板，每行生成一个独立的 xlsx 报表。

    模板单元格支持 ``{{列名}}``；文件名模板还支持 ``{{序号}}``、
    ``{{模板名}}``、``{{数据文件名}}``。整个单元格只有一个标记时，
    金额/日期会按原数据类型写入。
    """
    log = log or noop_log
    progress = progress or noop_progress

    if not output_dir:
        raise _template_error("请选择输出目录")
    _validate_template(template_path)
    frame, sheet_name = _read_data_source(data_path)
    if frame.empty:
        raise _template_error(
            "数据源没有可填充的数据行",
            hint="请确认数据源第一张工作表有表头和数据行。")

    markers = scan_template_markers(template_path)
    if not markers:
        raise _template_error(
            "模板中没有找到 {{标记}}",
            detail="单元格里需要使用 {{列名}} 形式的标记。",
            hint="例如在模板单元格写：{{姓名}}、{{金额}}、{{日期}}。",
        )

    data_columns = set(frame.columns)
    missing = [marker for marker in markers
               if marker not in data_columns and marker not in _SPECIAL_VALUES]
    if missing:
        log(f"⚠ 模板标记在数据源中找不到对应列：{'、'.join(missing)}", "warn")
        if len(missing) == len(markers):
            raise _template_error(
                "模板标记与数据列不匹配",
                detail=f"模板标记：{'、'.join(markers)}；数据列：{'、'.join(frame.columns)}",
                hint="请确认标记名称与数据源表头完全一致（区分空格和大小写）。",
            )

    filename_markers = [marker.strip() for marker in
                       _PLACEHOLDER_RE.findall(str(filename_template or ""))]
    filename_missing = [marker for marker in filename_markers
                        if marker not in data_columns
                        and marker not in _SPECIAL_VALUES]
    if filename_missing:
        log(f"⚠ 文件名模板中的标记找不到对应列："
            f"{'、'.join(filename_missing)}，这些位置会留空", "warn")

    os.makedirs(output_dir, exist_ok=True)
    total = len(frame)
    template_stem = os.path.splitext(os.path.basename(template_path))[0]
    data_stem = os.path.splitext(os.path.basename(data_path))[0]
    generated = 0
    skipped = 0
    failed = 0

    log(f"开始模板填充：{os.path.basename(data_path)} → {os.path.basename(template_path)}"
        f"（工作表：{sheet_name}，共 {total} 行）", "info")

    for index, (_, row) in enumerate(frame.iterrows(), start=1):
        values = _row_values(row, index, template_stem, data_stem)
        if skip_empty_rows and all(
                _text_value(values.get(column, "")) == "" for column in frame.columns):
            skipped += 1
            progress(index, total)
            continue

        filename = _render_filename(
            filename_template, values, fallback=f"报表_{index:03d}.xlsx")
        output_path = unique_path(os.path.join(output_dir, filename))
        try:
            _fill_one(template_path, output_path, values)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log(f"✗ 第 {index} 行生成失败：{os.path.basename(output_path)}"
                f"（{explain(exc).title}）", "error")
        else:
            generated += 1
            log(f"✓ 第 {index} 行：{os.path.basename(output_path)}", "success")
        progress(index, total)

    if generated == 0:
        raise _template_error(
            "没有生成任何报表",
            detail=f"共处理 {total} 行，失败 {failed} 行，跳过空行 {skipped} 行。",
            hint="请检查模板、数据源和文件名模板；若输出目录被占用，请关闭文件后重试。",
        )

    summary = (f"✔ 模板填充完成：生成 {generated} 份报表"
               f"（数据 {total} 行，跳过空行 {skipped}，失败 {failed}）"
               f" → {quote_path(output_dir)}")
    log(summary, "success")
    return {
        "files": generated,
        "rows": total,
        "skipped": skipped,
        "failed": failed,
        "output": output_dir,
    }
