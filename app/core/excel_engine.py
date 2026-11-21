"""Excel 底层读写封装（pandas + openpyxl + xlsxwriter）。"""
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

from .common import safe_sheet_name
from .errors import FriendlyError

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsm"}


def collect_files(paths: Iterable[str], recursive: bool = False) -> List[str]:
    """把文件 / 文件夹路径列表展开为 Excel 文件路径列表。"""
    result: List[str] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            for file in iterator:
                if (file.is_file()
                        and file.suffix.lower() in EXCEL_EXTENSIONS
                        and not file.name.startswith("~$")):
                    result.append(str(file))
        elif path.is_file() and path.suffix.lower() in EXCEL_EXTENSIONS:
            result.append(str(path))
    return sorted(set(result))


def read_workbook(path: str, dtype=None) -> Dict[str, pd.DataFrame]:
    """读取整个工作簿，返回 {工作表名: DataFrame}。

    ``dtype=object`` 可避免 pandas 把「00123」这类文本编号自动转成数字。
    """
    return pd.read_excel(path, sheet_name=None, dtype=dtype)


def _explicit_csv_encodings(encoding: str):
    value = str(encoding or "").strip().lower().replace("_", "-")
    if value in {"utf-8", "utf8", "utf-8-sig"}:
        return ["utf-8-sig"], "UTF-8"
    if value in {"gbk", "gb2312", "gb18030"}:
        return ["gbk", "gb18030"], "GBK"
    raise ValueError(f"不支持的 CSV 编码：{encoding}")


def read_csv_smart(path: str,
                   nrows: Optional[int] = None,
                   encoding: Optional[str] = None) -> pd.DataFrame:
    """读取 CSV；``encoding`` 指定 UTF-8 / GBK 时不再自动猜测。

    ``nrows`` 有值时只读取前若干行（用于预览）。
    """
    explicit_label = ""
    if encoding and str(encoding).lower() not in {"auto", "automatic", "自动"}:
        encodings, explicit_label = _explicit_csv_encodings(encoding)
    else:
        encodings = ["utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "latin-1"]
        try:
            with open(path, "rb") as fp:
                raw = fp.read(65536)
        except OSError:
            raw = b""
        try:
            import chardet
            guess = (chardet.detect(raw) or {}).get("encoding")
            if guess:
                encodings.insert(0, guess)
        except Exception:  # noqa: BLE001
            pass

    last_error = None
    for candidate in encodings:
        try:
            return pd.read_csv(path, encoding=candidate, nrows=nrows)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except Exception as exc:  # noqa: BLE001
            raise FriendlyError(
                "无法解析 CSV 文件",
                detail="读取文件内容时发生异常。",
                hint="请确认文件没有被其他程序占用，且内容确实是文本格式的 CSV；"
                     "若反复失败，请查看项目目录下 logs/error.log。",
            ) from exc

    if explicit_label:
        raise FriendlyError(
            f"无法按 {explicit_label} 编码读取 CSV 文件",
            detail="文件内容与所选编码不匹配，可能选错了编码。",
            hint="请尝试把 CSV 编码切换为 UTF-8 或 GBK 后重试。",
        ) from last_error
    raise FriendlyError(
        "无法识别 CSV 文件的编码",
        detail="尝试了 UTF-8、GBK 等常见编码仍无法读取该文件。",
        hint="请用记事本把文件另存为 UTF-8 编码后重试。",
    ) from last_error


def _autofit(worksheet, df: pd.DataFrame) -> None:
    """根据内容估算列宽。"""
    for idx, column in enumerate(df.columns):
        try:
            sample = df[column].astype(str).head(200)
            width = max(len(str(column)), int(sample.str.len().max() or 8))
        except Exception:  # noqa: BLE001
            width = 12
        worksheet.set_column(idx, idx, min(max(width + 2, 8), 42))


def write_workbook(frames: Dict[str, pd.DataFrame], path: str) -> str:
    """把多张 DataFrame 写入同一个 Excel 文件。"""
    if not frames:
        raise ValueError("没有可写出的数据")
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)

    used = set()
    with pd.ExcelWriter(path, engine="xlsxwriter",
                        datetime_format="yyyy-mm-dd") as writer:
        for raw_name, df in frames.items():
            name = safe_sheet_name(raw_name)
            base, index = name, 1
            while name in used:
                name = safe_sheet_name(f"{base[:28]}_{index}")
                index += 1
            used.add(name)
            df.to_excel(writer, sheet_name=name, index=False)
            _autofit(writer.sheets[name], df)
    return path


def write_dataframe(df, output_path, sheet_name="Sheet1"):
    folder = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(folder, exist_ok=True)
    try:
        df.to_excel(output_path, index=False, sheet_name=sheet_name)
    except FileNotFoundError as exc:
        folder = os.path.dirname(os.path.abspath(output_path))
        raise FriendlyError(
            "保存位置不存在",
            detail=f"找不到输出目录：{folder}",
            hint="请重新选择输出位置，或先手动创建目标文件夹后重试。",
        ) from exc
    except OSError:
        # 交给统一异常翻译，给出“文件被占用 / 无权限 / 路径无效”等中文提示
        raise
    except Exception as exc:  # noqa: BLE001
        raise FriendlyError(
            f"无法保存表格：{os.path.basename(output_path)}",
            detail="写入文件时发生异常，可能是文件格式或磁盘问题。",
            hint="请确认输出目录可写、文件未被占用；若反复失败，请查看项目目录下 logs/error.log。",
        ) from exc