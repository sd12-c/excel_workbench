"""文件预览数据读取：只读取前若干行，供界面表格展示。"""
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pandas as pd

from .errors import FriendlyError
from .excel_engine import EXCEL_EXTENSIONS, read_csv_smart

PREVIEW_ROWS = 20
_CSV_EXTENSIONS = {".csv"}
_PREVIEW_EXTENSIONS = EXCEL_EXTENSIONS | _CSV_EXTENSIONS


@dataclass
class PreviewData:
    """一次预览所需的列名与前若干行数据（均已转成字符串）。"""

    columns: List[str]
    rows: List[List[str]]
    sheet_names: List[str] = field(default_factory=list)
    sheet_name: str = ""


def is_previewable(path: str) -> bool:
    """是否属于当前支持预览的文件类型。"""
    return os.path.splitext(str(path))[1].lower() in _PREVIEW_EXTENSIONS


def read_preview(path: str,
                 sheet_name: Optional[str] = None,
                 rows: int = PREVIEW_ROWS) -> PreviewData:
    """读取预览数据；Excel 可指定工作表，CSV 视为单表。"""
    extension = os.path.splitext(str(path))[1].lower()
    if extension == ".csv":
        frame = read_csv_smart(path, nrows=rows)
        columns, table_rows = _to_table(frame)
        return PreviewData(columns, table_rows)

    if extension not in EXCEL_EXTENSIONS:
        raise ValueError(f"不支持预览的文件类型：{extension or '未知'}")

    with pd.ExcelFile(path) as workbook:
        sheet_names = [str(name) for name in workbook.sheet_names]
        if not sheet_names:
            raise FriendlyError(
                "文件里没有工作表",
                detail="该 Excel 文件不包含任何工作表。",
                hint="请用 Excel 打开确认文件内容完整后重试。",
            )
        target = sheet_name if sheet_name in sheet_names else sheet_names[0]
        frame = pd.read_excel(workbook, sheet_name=target, nrows=rows)

    columns, table_rows = _to_table(frame)
    return PreviewData(columns, table_rows, sheet_names, target or "")


def _to_table(frame: pd.DataFrame) -> Tuple[List[str], List[List[str]]]:
    columns = [str(column) for column in frame.columns]
    rows = [[_cell_text(value) for value in record]
            for record in frame.itertuples(index=False, name=None)]
    return columns, rows


def _cell_text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        if (value.hour, value.minute, value.second) == (0, 0, 0):
            return value.strftime("%Y-%m-%d")
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)
