"""简易数据透视：选择行、列、值和聚合方式，生成新的 xlsx 透视表。"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from .common import noop_log, noop_progress, quote_path, unique_path
from .errors import FriendlyError, explain
from .excel_engine import read_csv_smart, read_workbook, write_dataframe

AGGREGATIONS = {
    "sum": "求和",
    "count": "计数",
    "mean": "平均值",
}
AGGREGATION_CHOICES = list(AGGREGATIONS.items())


def _source_error(message: str, detail: str = "", hint: str = "") -> FriendlyError:
    return FriendlyError(message, detail=detail, hint=hint)


def list_pivot_sheets(path: str) -> List[str]:
    """列出可透视的工作表；CSV 视为单表 CSV。"""
    if not path:
        raise _source_error("请选择数据源")
    if not os.path.exists(path):
        raise _source_error("找不到数据源文件", detail=path)
    extension = os.path.splitext(path)[1].lower()
    if extension == ".csv":
        return ["CSV"]
    if extension not in {".xlsx", ".xls", ".xlsm"}:
        raise _source_error(
            "不支持的数据源格式",
            detail=f"当前文件：{os.path.basename(path)}",
            hint="支持 .xlsx、.xls、.xlsm 和 .csv。",
        )
    try:
        with pd.ExcelFile(path) as workbook:
            return [str(name) for name in workbook.sheet_names]
    except Exception as exc:  # noqa: BLE001
        raise _source_error(
            "无法读取数据源工作表",
            detail=explain(exc).title,
            hint="请确认文件没有被占用，且格式正确。",
        ) from exc


def read_pivot_columns(path: str, sheet_name: Optional[str] = None) -> List[str]:
    """只读取表头，供界面填充行/列/值下拉框。"""
    if not path:
        raise _source_error("请选择数据源")
    extension = os.path.splitext(path)[1].lower()
    try:
        if extension == ".csv":
            frame = read_csv_smart(path, nrows=0)
        else:
            sheets = list_pivot_sheets(path)
            target = sheet_name if sheet_name in sheets else sheets[0]
            frame = pd.read_excel(path, sheet_name=target, nrows=0)
    except FriendlyError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise _source_error(
            "无法读取数据源列名",
            detail=explain(exc).title,
            hint="请确认数据源第一行是列名，且文件没有被占用。",
        ) from exc
    return [str(column).strip() for column in frame.columns]


def _read_pivot_source(path: str,
                       sheet_name: Optional[str]) -> tuple[pd.DataFrame, str]:
    extension = os.path.splitext(path)[1].lower()
    if extension == ".csv":
        try:
            frame = read_csv_smart(path).astype(object)
        except Exception as exc:  # noqa: BLE001
            raise _source_error(
                "无法读取 CSV 数据源",
                detail=explain(exc).title,
                hint="请确认 CSV 编码正确，并在必要时选择 UTF-8 / GBK。",
            ) from exc
        return frame, "CSV"

    try:
        workbook = read_workbook(path, dtype=object)
    except Exception as exc:  # noqa: BLE001
        raise _source_error(
            "无法读取 Excel 数据源",
            detail=explain(exc).title,
            hint="请确认文件没有被占用，且内容格式正确。",
        ) from exc
    if not workbook:
        raise _source_error(
            "数据源里没有工作表",
            hint="请用 Excel 打开数据源，确认至少有一张工作表。")
    if sheet_name and sheet_name in workbook:
        name = sheet_name
    else:
        name = next(iter(workbook))
    return workbook[name], str(name)


def build_pivot(data_path: str,
                sheet_name: Optional[str],
                row_field: str,
                column_field: str,
                value_field: str,
                aggfunc: str,
                output_path: str,
                progress: Optional[Callable[[int, int], None]] = None,
                log: Optional[Callable[[str, str], None]] = None) -> dict:
    """生成透视表并写出新的 xlsx 文件。

    ``column_field`` 可以为空，表示不设置列字段；
    ``aggfunc`` 支持 sum / count / mean。
    """
    log = log or noop_log
    progress = progress or noop_progress

    if not data_path:
        raise _source_error("请选择数据源")
    if not output_path:
        raise _source_error("请选择输出文件")
    if aggfunc not in AGGREGATIONS:
        raise ValueError(f"不支持的聚合方式：{aggfunc}")
    row_field = str(row_field or "").strip()
    column_field = str(column_field or "").strip()
    value_field = str(value_field or "").strip()
    if not row_field:
        raise _source_error("请选择行字段")
    if not value_field:
        raise _source_error("请选择值字段")
    if row_field == value_field:
        raise _source_error("行字段和值字段不能是同一列")
    if column_field and column_field in {row_field, value_field}:
        raise _source_error(
            "列字段不能和行字段或值字段重复",
            hint="请选择另一列作为列字段，或把列字段留空。")

    progress(0, 1)
    frame, actual_sheet = _read_pivot_source(data_path, sheet_name)
    frame = frame.copy()
    frame.columns = [str(column).strip() for column in frame.columns]
    frame = frame.dropna(how="all").reset_index(drop=True)
    if frame.empty:
        raise _source_error(
            "数据源没有可透视的数据行",
            hint="请确认工作表第一行是列名，后面有数据。")

    for field in (row_field, value_field):
        if field not in frame.columns:
            raise _source_error(
                f"数据源缺少列：{field}",
                detail=f"可用列：{'、'.join(frame.columns)}",
                hint="请重新选择字段，或检查表头名称。")
    if column_field and column_field not in frame.columns:
        raise _source_error(
            f"数据源缺少列：{column_field}",
            detail=f"可用列：{'、'.join(frame.columns)}",
            hint="请重新选择列字段，或把列字段设为“不使用”。")

    working = frame.copy()
    ignored_values = 0
    if aggfunc in {"sum", "mean"}:
        original_blank = working[value_field].isna().sum()
        numeric = pd.to_numeric(working[value_field], errors="coerce")
        ignored_values = int(numeric.isna().sum() - original_blank)
        working[value_field] = numeric
        if numeric.notna().sum() == 0:
            raise _source_error(
                f"值字段“{value_field}”没有可用数字",
                hint="求和/平均值需要数字列；文本列可以改用“计数”。")
        if ignored_values:
            log(f"⚠ 值字段“{value_field}”有 {ignored_values} 个值无法转成数字，"
                "已从求和/平均值中忽略", "warn")

    fill_value = 0 if aggfunc in {"sum", "count"} else None
    try:
        pivot = pd.pivot_table(
            working,
            index=row_field,
            columns=column_field or None,
            values=value_field,
            aggfunc=aggfunc,
            fill_value=fill_value,
            dropna=False,
            sort=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise _source_error(
            "无法生成透视表",
            detail=explain(exc).title,
            hint="请检查行、列、值字段是否适合当前数据；值字段为文本时可尝试“计数”。",
        ) from exc

    if pivot.empty:
        raise _source_error(
            "透视结果为空",
            hint="请检查行字段、列字段和值字段是否有数据。")

    if isinstance(pivot.columns, pd.MultiIndex):
        pivot.columns = [
            "_".join(str(part) for part in item if str(part) != "")
            for item in pivot.columns
        ]
    else:
        pivot.columns = [str(item) for item in pivot.columns]

    if column_field:
        pivot.columns = [f"{AGGREGATIONS[aggfunc]}:{item}"
                         for item in pivot.columns]
    else:
        pivot.columns = [f"{AGGREGATIONS[aggfunc]}:{value_field}"]

    pivot = pivot.reset_index()
    pivot.columns = [str(column).strip() for column in pivot.columns]

    if not output_path.lower().endswith(".xlsx"):
        output_path += ".xlsx"
    output_path = unique_path(output_path)
    try:
        write_dataframe(pivot, output_path, sheet_name="透视表")
    except Exception as exc:  # noqa: BLE001
        raise _source_error(
            "保存透视表失败",
            detail=explain(exc).title,
            hint="请确认输出文件没有被占用，且目录可写。",
        ) from exc

    log(f"ℹ 数据源：{os.path.basename(data_path)} [{actual_sheet}]，"
        f"共 {len(frame)} 行", "info")
    log(f"✔ 已生成透视表：{len(pivot)} 行 × {len(pivot.columns)} 列"
        f" → {quote_path(output_path)}", "success")
    progress(1, 1)
    return {
        "rows": len(pivot),
        "columns": len(pivot.columns),
        "source_rows": len(frame),
        "ignored_values": ignored_values,
        "sheet": actual_sheet,
        "output": output_path,
    }
