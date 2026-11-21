"""CSV ↔ Excel 互转。"""
import os
from typing import Callable, List, Optional

from .common import noop_log, noop_progress, quote_path, safe_sheet_name, unique_path
from .errors import FriendlyError, explain
from .excel_engine import read_csv_smart, read_workbook, write_dataframe


# --------------------------------------------------------------------------- #
# CSV → Excel
# --------------------------------------------------------------------------- #
def csv_to_excel(files: List[str],
                 output_dir: str,
                 encoding: str = "auto",
                 progress: Optional[Callable[[int, int], None]] = None,
                 log: Optional[Callable[[str, str], None]] = None) -> dict:
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加 CSV 文件")
    os.makedirs(output_dir, exist_ok=True)

    if encoding and str(encoding).lower() != "auto":
        log(f"ℹ CSV 读取编码：{str(encoding).upper()}", "info")

    total = max(len(files), 1)
    count = 0
    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        try:
            frame = read_csv_smart(path, encoding=encoding)
        except Exception as exc:  # noqa: BLE001
            log(f"✗ 读取失败：{name}（{explain(exc).title}）", "error")
            progress(index, total)
            continue
        out_path = unique_path(os.path.join(
            output_dir, f"{os.path.splitext(name)[0]}.xlsx"))
        write_dataframe(frame, out_path, sheet_name=safe_sheet_name(os.path.splitext(name)[0]))
        count += 1
        log(f"✓ CSV → Excel：{name} → {quote_path(out_path)}", "success")
        progress(index, total)

    if count == 0:
        raise FriendlyError(
            "没有 CSV 文件转换成功",
            detail="所有文件都读取失败，可能是 CSV 编码选择不正确。",
            hint="请尝试把 CSV 编码切换为 UTF-8 或 GBK 后重试。",
        )

    log(f"✔ 转换完成：共输出 {count} 个 Excel 文件 → {quote_path(output_dir)}", "success")
    return {"files": count, "encoding": encoding, "output": output_dir}


# --------------------------------------------------------------------------- #
# Excel → CSV
# --------------------------------------------------------------------------- #
def excel_to_csv(files: List[str],
                 output_dir: str,
                 all_sheets: bool = True,
                 encoding: str = "utf-8-sig",
                 progress: Optional[Callable[[int, int], None]] = None,
                 log: Optional[Callable[[str, str], None]] = None) -> dict:
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加 Excel 文件")
    os.makedirs(output_dir, exist_ok=True)

    total = max(len(files), 1)
    count = 0
    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        stem = os.path.splitext(name)[0]
        try:
            workbook = read_workbook(path)
        except Exception as exc:  # noqa: BLE001
            log(f"✗ 读取失败：{name}（{explain(exc).title}）", "error")
            progress(index, total)
            continue

        items = list(workbook.items()) if all_sheets else [next(iter(workbook.items()))]
        for sheet_name, frame in items:
            suffix = f"_{sheet_name}" if all_sheets and len(workbook) > 1 else ""
            out_path = unique_path(os.path.join(output_dir, f"{stem}{suffix}.csv"))
            try:
                frame.to_csv(out_path, index=False, encoding=encoding)
                count += 1
            except Exception as exc:  # noqa: BLE001
                log(f"✗ 写出失败：{quote_path(out_path)}（{explain(exc).title}）", "error")
        log(f"✓ Excel → CSV：{name}", "success")
        progress(index, total)

    log(f"✔ 转换完成：共输出 {count} 个 CSV 文件 → {quote_path(output_dir)}", "success")
    return {"files": count, "output": output_dir}
