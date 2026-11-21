"""多文件 / 多工作表合并。"""
import os
from typing import Callable, List, Optional, Tuple

import pandas as pd

from .common import noop_log, noop_progress, quote_path, split_csv_line
from .errors import FriendlyError, explain, record_exception
from .excel_engine import write_dataframe

ALIGNMENT_UNION = "union"
ALIGNMENT_INTERSECTION = "intersection"


def merge_files(files: List[str],
                output_path: str,
                all_sheets: bool = True,
                add_source: bool = True,
                source_column: str = "来源文件",
                sheet_column: str = "来源工作表",
                alignment: str = ALIGNMENT_UNION,
                ignore_empty_sheets: bool = True,
                sort_columns: Optional[str] = "",
                sort_ascending: bool = True,
                progress: Optional[Callable[[int, int], None]] = None,
                log: Optional[Callable[[str, str], None]] = None) -> dict:
    """合并多个 Excel 文件为一张总表。

    ``alignment``：
      - ``union``：按表头合并，保留所有出现过的列，缺少的单元格留空；
      - ``intersection``：只保留所有文件共有的列（按每个文件所有采纳工作表计算）。
    """
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加需要合并的 Excel 文件")
    if alignment not in {ALIGNMENT_UNION, ALIGNMENT_INTERSECTION}:
        raise ValueError("未知的列对齐策略")

    source_column = (source_column or "").strip() or "来源文件"
    sheet_column = (sheet_column or "").strip() or "来源工作表"
    if add_source and all_sheets and source_column == sheet_column:
        raise FriendlyError(
            "来源文件列与来源工作表列不能同名",
            detail=f"两个来源列都叫「{source_column}」。",
            hint="请修改来源列名称，或取消勾选「添加来源列」。",
        )

    total = max(len(files), 1)
    entries: List[Tuple[str, str, pd.DataFrame]] = []
    file_column_sets: List[List[str]] = []
    failed = 0

    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        try:
            workbook = pd.read_excel(path, sheet_name=None)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log(f"✗ 读取失败：{name}（{explain(exc).title}）", "error")
            progress(index, total)
            continue

        if all_sheets:
            items = list(workbook.items())
        else:
            first_key = next(iter(workbook))
            items = [(first_key, workbook[first_key])]

        kept = 0
        current_columns: List[str] = []
        for sheet_name, frame in items:
            if frame is None:
                continue
            if ignore_empty_sheets and frame.dropna(how="all").empty:
                continue
            frame = frame.copy()
            frame.columns = [str(c).strip() for c in frame.columns]
            entries.append((name, str(sheet_name), frame))
            current_columns.extend(str(c) for c in frame.columns)
            kept += 1

        if current_columns:
            file_column_sets.append(list(dict.fromkeys(current_columns)))

        log(f"✓ {name}：共 {len(workbook)} 个工作表，采纳 {kept} 个", "success")
        progress(index, total)

    if not entries:
        raise FriendlyError(
            "没有可合并的数据",
            detail="所有文件都没有可合并的工作表或数据行。",
            hint="请检查文件内容；如果是空表，可取消勾选「忽略空工作表 / 空数据」后重试。",
        )

    # 1. 列对齐
    if alignment == ALIGNMENT_INTERSECTION:
        common_columns = _common_columns(file_column_sets)
        if not common_columns:
            raise FriendlyError(
                "所有文件没有共同的列",
                detail="各文件的表头完全不一致，无法使用「只保留共有列」策略。",
                hint="请改用「按表头合并」，或先把各文件的列名统一。",
            )
        entries = [(name, sheet, frame.reindex(columns=common_columns))
                   for name, sheet, frame in entries]
        log(f"ℹ 列对齐：仅保留所有文件共有的 {len(common_columns)} 列", "info")
    else:
        log("ℹ 列对齐：按表头合并，缺少的列自动填空", "info")

    # 2. 添加来源列
    if add_source:
        _check_source_columns(entries, all_sheets, source_column, sheet_column)
        frames: List[pd.DataFrame] = []
        for name, sheet_name, frame in entries:
            frame.insert(0, source_column, name)
            if all_sheets:
                frame.insert(1, sheet_column, sheet_name)
            frames.append(frame)
    else:
        frames = [frame for _, _, frame in entries]

    # 3. 合并数据
    merged = pd.concat(frames, ignore_index=True, sort=False)
    merged = merged.dropna(axis=1, how="all")

    # 4. 按指定列排序
    target_cols = split_csv_line(sort_columns) if sort_columns else []
    if target_cols:
        valid_cols = [c for c in target_cols if c in merged.columns]
        missing_cols = [c for c in target_cols if c not in merged.columns]

        if missing_cols:
            log(f"⚠ 以下排序列不存在，已忽略：{'、'.join(missing_cols)}", "warn")

        if valid_cols:
            try:
                # 针对日期列做智能转换，防止日期被当字符串排序
                for col in valid_cols:
                    if "日期" in col or "时间" in col:
                        parsed = pd.to_datetime(merged[col], errors="coerce")
                        # 如果转换成功率大于 50%，则采用转换后的时间进行排序
                        if parsed.notna().mean() > 0.5:
                            merged[f"__sort_{col}"] = parsed
                            valid_cols[valid_cols.index(col)] = f"__sort_{col}"

                # 使用 mergesort 稳定排序，保证相同值的数据保持原有的追加顺序
                merged = merged.sort_values(
                    by=valid_cols,
                    ascending=sort_ascending,
                    kind="mergesort",
                    na_position="last"
                )

                # 清理辅助排序列
                temp_cols = [c for c in merged.columns if c.startswith("__sort_")]
                if temp_cols:
                    merged = merged.drop(columns=temp_cols)

                merged = merged.reset_index(drop=True)
                direction = "升序" if sort_ascending else "降序"
                log(f"✔ 已按 [{', '.join(target_cols)}] 进行{direction}排序", "success")
            except Exception as exc:  # noqa: BLE001
                record_exception(exc, "合并排序")
                log("⚠ 排序失败（可能存在无法比较的数据类型），已按原顺序输出", "warn")

    # 5. 写出结果
    write_dataframe(merged, output_path, sheet_name="合并结果")

    log(f"✔ 合并完成：{len(merged)} 行 × {len(merged.columns)} 列 → {quote_path(output_path)}",
        "success")
    return {
        "rows": len(merged),
        "cols": len(merged.columns),
        "files": len(files),
        "failed": failed,
        "alignment": alignment,
        "output": output_path,
    }


def _common_columns(file_column_sets: List[List[str]]) -> List[str]:
    """按文件计算列交集，并保持列在文件中首次出现的顺序。"""
    if not file_column_sets:
        return []
    common = set(file_column_sets[0])
    for columns in file_column_sets[1:]:
        common &= set(columns)
    if not common:
        return []

    ordered: List[str] = []
    for columns in file_column_sets:
        for column in columns:
            if column in common and column not in ordered:
                ordered.append(column)
    return ordered


def _check_source_columns(entries: List[Tuple[str, str, pd.DataFrame]],
                          all_sheets: bool,
                          source_column: str,
                          sheet_column: str) -> None:
    """插入来源列前检查重名，避免 pandas 抛出难以理解的错误。"""
    for _name, _sheet, frame in entries:
        if source_column in frame.columns:
            raise FriendlyError(
                f"来源列名「{source_column}」与表格中已有的列重名",
                detail="合并结果会出现两个同名列，无法区分数据来源。",
                hint="请换一个来源文件列名，或取消勾选「添加来源列」。",
            )
        if all_sheets and sheet_column in frame.columns:
            raise FriendlyError(
                f"来源列名「{sheet_column}」与表格中已有的列重名",
                detail="合并结果会出现两个同名列，无法区分数据来源。",
                hint="请换一个来源工作表列名，或取消勾选「添加来源列」。",
            )
