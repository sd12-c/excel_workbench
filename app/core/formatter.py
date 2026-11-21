"""批量格式统一：清空行 / 去重 / 日期规范化 / 去空格 / 清理链接批注 / 数字统一。"""
import os
import re
import unicodedata
import zipfile
from datetime import date, datetime
from typing import Callable, List, Mapping, Optional, Sequence

import pandas as pd

from . import clean_rules
from .common import noop_log, noop_progress, quote_path, unique_path
from .errors import explain
from .excel_engine import read_workbook

MAX_DATE_ERROR_LOGS = 20
_DATE_MARKER_RE = re.compile(
    r"(?:19|20)\d{2}\s*[-/.年]|\d{1,2}\s*月|\d{1,2}\s*[日号]")
_CN_FULL_DATE_RE = re.compile(
    r"^(\d{4})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*[日号]?$")
_CN_MONTH_DAY_RE = re.compile(r"^(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?$")
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_LEADING_ZERO_RE = re.compile(r"^[+-]?0\d")
_CURRENCY_CHARS = "¥￥$€£"


# --------------------------------------------------------------------------- #
# 数字统一
# --------------------------------------------------------------------------- #
def _normalize_number_text(value):
    """把文本数字转成 int / float；不像数字或需要保留原样的返回 None。"""
    if not isinstance(value, str):
        return None

    text = unicodedata.normalize("NFKC", value).strip()
    if not text or text.startswith("+"):
        return None
    if "%" in text or "‰" in text:
        return None

    for char in _CURRENCY_CHARS:
        text = text.replace(char, "")
    text = text.replace(",", "").replace("，", "")
    text = "".join(text.split())
    if not text or not _NUMBER_RE.match(text):
        return None

    digits = "".join(char for char in text if char.isdigit())
    if not digits or len(digits) > 15:
        return None
    if _LEADING_ZERO_RE.match(text):
        return None
    if "." not in text and "e" not in text.lower() and len(digits) >= 11:
        return None

    try:
        if "." in text or "e" in text.lower():
            return float(text)
        return int(text)
    except ValueError:
        return None


def _normalize_number_series(series: pd.Series):
    """统一一列中的文本数字，返回 (新列, 转换数量)。"""
    if (pd.api.types.is_numeric_dtype(series)
            or pd.api.types.is_datetime64_any_dtype(series)):
        return series, 0

    values = []
    converted = 0
    for value in series:
        number = _normalize_number_text(value)
        if number is None:
            values.append(value)
        else:
            values.append(number)
            converted += 1
    if converted == 0:
        return series, 0
    return pd.Series(values, index=series.index, dtype=object), converted


# --------------------------------------------------------------------------- #
# 日期识别
# --------------------------------------------------------------------------- #
def _is_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


def _parse_chinese_date(text: str, default_year: int) -> Optional[pd.Timestamp]:
    match = _CN_FULL_DATE_RE.match(text)
    if match:
        year, month, day = (int(part) for part in match.groups())
    else:
        match = _CN_MONTH_DAY_RE.match(text)
        if not match:
            return None
        year = default_year
        month, day = (int(part) for part in match.groups())

    try:
        return pd.Timestamp(datetime(year, month, day))
    except ValueError:
        return None


def _coerce_date(value, default_year: int, recognize_chinese: bool):
    if _is_blank(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, datetime):
        return pd.Timestamp(value)
    if isinstance(value, date):
        return pd.Timestamp(value)
    if not isinstance(value, str):
        return None

    text = unicodedata.normalize("NFKC", value).strip()
    if not text:
        return None
    if recognize_chinese:
        parsed = _parse_chinese_date(text, default_year)
        if parsed is not None:
            return parsed
    try:
        parsed = pd.to_datetime(text, errors="raise")
    except Exception:  # noqa: BLE001
        return None
    if pd.isna(parsed):
        return None
    return parsed


def _looks_like_dates(series: pd.Series, recognize_chinese: bool) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna()
    if sample.empty:
        return False
    if not (pd.api.types.is_object_dtype(sample)
            or pd.api.types.is_string_dtype(sample)):
        return False

    values = list(sample.head(60))
    joined = " ".join(str(value) for value in values)
    if not _DATE_MARKER_RE.search(joined):
        return False

    default_year = datetime.now().year
    parsed = sum(
        1 for value in values
        if _coerce_date(value, default_year, recognize_chinese) is not None)
    return parsed / len(values) >= 0.8


def _normalize_date_series(series: pd.Series,
                           fmt: str,
                           recognize_chinese: bool):
    """格式化日期列，返回 (新列, 失败行列表[(Excel行号, 原值)])。"""
    default_year = datetime.now().year
    values = []
    failures = []

    for position, original in enumerate(series):
        if _is_blank(original):
            values.append(original)
            continue

        parsed = _coerce_date(original, default_year, recognize_chinese)
        if parsed is None:
            values.append(original)
            failures.append((position + 2, original))
            continue
        try:
            values.append(parsed.strftime(fmt))
        except (AttributeError, ValueError):
            values.append(original)
            failures.append((position + 2, original))

    return pd.Series(values, index=series.index, dtype=object), failures


def _valid_date_format(fmt: str) -> bool:
    try:
        datetime.now().strftime(fmt)
        return True
    except (TypeError, ValueError):
        return False


def _short_repr(value, limit: int = 48) -> str:
    text = " ".join(repr(value).split())
    return text if len(text) <= limit else text[:limit] + "…"


def _log_date_failures(log, name: str, sheet_name: str,
                       column: str, failures) -> None:
    for row_number, value in failures[:MAX_DATE_ERROR_LOGS]:
        log(f"⚠ 日期识别失败：{name} [{sheet_name}] 第 {row_number} 行"
            f"「{column}」= {_short_repr(value)}，已保留原值", "warn")
    if len(failures) > MAX_DATE_ERROR_LOGS:
        log(f"⚠ {name} [{sheet_name}]「{column}」还有 "
            f"{len(failures) - MAX_DATE_ERROR_LOGS} 行日期识别失败未逐行显示",
            "warn")


# --------------------------------------------------------------------------- #
# 超链接 / 批注清理（输出为纯数据，不保留链接与批注）
# --------------------------------------------------------------------------- #
def _count_tag_in_zip(archive: zipfile.ZipFile, name: str, tag: bytes) -> int:
    """分块统计压缩包内某个 XML 文件中的标签数量，避免一次性读入大文件。"""
    total = 0
    buffer = b""
    keep = max(len(tag) - 1, 0)
    with archive.open(name) as fp:
        while True:
            chunk = fp.read(65536)
            if not chunk:
                break
            data = buffer + chunk
            total += data.count(tag)
            buffer = data[-keep:] if keep else b""
    return total


def _count_removed_objects(path: str, count_links: bool, count_comments: bool):
    """统计源文件中的超链接 / 批注数量（仅 xlsx/xlsm，失败时返回 0）。"""
    if os.path.splitext(path)[1].lower() not in {".xlsx", ".xlsm"}:
        return 0, 0

    links = 0
    comments = 0
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                lowered = name.lower()
                if (count_links
                        and lowered.startswith("xl/worksheets/")
                        and lowered.endswith(".xml")):
                    links += _count_tag_in_zip(archive, name, b"<hyperlink ")
                elif (count_comments
                      and lowered.startswith("xl/comments")
                      and lowered.endswith(".xml")):
                    comments += _count_tag_in_zip(archive, name, b"<comment ")
    except Exception:  # noqa: BLE001
        return 0, 0
    return links, comments


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def format_files(files: List[str],
                 output_dir: str,
                 remove_empty_rows: bool = True,
                 remove_empty_cols: bool = False,
                 strip_text: bool = False,
                 clear_hyperlinks: bool = False,
                 clear_comments: bool = False,
                 normalize_numbers: bool = False,
                 drop_duplicates: bool = False,
                 dedup_columns: Optional[Sequence[str]] = None,
                 normalize_date: bool = True,
                 recognize_chinese_dates: bool = True,
                 date_columns: Optional[Sequence[str]] = None,
                 date_format: str = "%Y-%m-%d",
                 all_sheets: bool = True,
                 progress: Optional[Callable[[int, int], None]] = None,
                 log: Optional[Callable[[str, str], None]] = None,
                 global_rules: Optional[Sequence[str]] = None,
                 column_bindings: Optional[Sequence[Mapping]] = None) -> dict:
    """批量清洗并另存为新的 Excel 文件。"""
    log = log or noop_log
    progress = progress or noop_progress

    if not files:
        raise ValueError("请先添加需要处理的 Excel 文件")

    date_format = str(date_format or "%Y-%m-%d").strip() or "%Y-%m-%d"

    # global_rules=None 时兼容旧调用方，用旧布尔参数生成规则列表。
    if global_rules is None:
        global_rules = clean_rules.legacy_global_rules(
            remove_empty_rows=remove_empty_rows,
            remove_empty_cols=remove_empty_cols,
            strip_text=strip_text,
            clear_hyperlinks=clear_hyperlinks,
            clear_comments=clear_comments,
            normalize_numbers=normalize_numbers,
            drop_duplicates=drop_duplicates,
            normalize_date=normalize_date,
        )
    else:
        global_rules = clean_rules.normalize_global_rules(global_rules)
    bindings = clean_rules.normalize_column_bindings(column_bindings)

    has_date_rule = (
        "normalize_dates" in global_rules
        or any(binding.rule == "date" for binding in bindings)
    )
    if has_date_rule and not clean_rules.valid_date_format(date_format):
        log(f"✗ 日期格式无效：{date_format}，已跳过日期统一", "error")
        global_rules = [key for key in global_rules
                        if key != "normalize_dates"]
        bindings = [binding for binding in bindings
                    if binding.rule != "date"]

    clear_hyperlinks = "clear_hyperlinks" in global_rules
    clear_comments = "clear_comments" in global_rules

    os.makedirs(output_dir, exist_ok=True)
    total = max(len(files), 1)
    stats = {
        "files": 0,
        "removed_rows": 0,
        "removed_dups": 0,
        "date_cols": 0,
        "date_failures": 0,
        "numbers": 0,
        "phones": 0,
        "hyperlinks": 0,
        "comments": 0,
    }

    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        try:
            workbook = read_workbook(path)
        except Exception as exc:  # noqa: BLE001
            log(f"✗ 读取失败：{name}（{explain(exc).title}）", "error")
            progress(index, total)
            continue

        file_links = 0
        file_comments = 0
        if clear_hyperlinks or clear_comments:
            counted_links, counted_comments = _count_removed_objects(
                path, clear_hyperlinks, clear_comments)
            if clear_hyperlinks:
                file_links = counted_links
                stats["hyperlinks"] += file_links
            if clear_comments:
                file_comments = counted_comments
                stats["comments"] += file_comments

        file_numbers = 0
        numbers_before = stats["numbers"]
        phones_before = stats["phones"]
        out_frames = {}
        for sheet_name, frame in workbook.items():
            if not all_sheets and out_frames:
                break
            before = len(frame)
            frame = frame.copy()
            frame.columns = [str(c).strip() for c in frame.columns]

            # 1. 全局规则统一先执行
            frame = clean_rules.apply_global_rules(
                frame, global_rules,
                dedup_columns=dedup_columns or (),
                date_columns=date_columns or (),
                date_format=date_format,
                recognize_chinese_dates=recognize_chinese_dates,
                file_name=name,
                sheet_name=sheet_name,
                log=log,
                stats=stats,
            )
            # 2. 再执行用户配置的单列绑定规则
            frame = clean_rules.apply_column_bindings(
                frame, bindings,
                date_format=date_format,
                recognize_chinese_dates=recognize_chinese_dates,
                file_name=name,
                sheet_name=sheet_name,
                log=log,
                stats=stats,
            )

            frame = frame.reset_index(drop=True)
            stats["removed_rows"] += max(before - len(frame), 0)
            out_frames[sheet_name] = frame

        if not out_frames:
            log(f"⚠ {name}：没有可处理的内容", "warn")
            progress(index, total)
            continue

        file_numbers = stats["numbers"] - numbers_before
        file_phones = stats["phones"] - phones_before
        if file_links or file_comments:
            parts = []
            if file_links:
                parts.append(f"超链接 {file_links} 个")
            if file_comments:
                parts.append(f"批注 {file_comments} 个")
            log(f"ℹ {name}：已清除" + "、".join(parts), "info")
        if file_numbers:
            log(f"ℹ {name}：数字格式统一，转换 {file_numbers} 个单元格", "info")
        if file_phones:
            log(f"ℹ {name}：已规范化 {file_phones} 个手机号列", "info")

        out_path = unique_path(os.path.join(output_dir, f"cleaned_{os.path.splitext(name)[0]}.xlsx"))
        clean_rules.write_clean_output(
            out_frames, out_path, bindings, date_format=date_format)

        stats["files"] += 1
        log(f"✓ 已清洗：{name} → {quote_path(out_path)}", "success")
        progress(index, total)

    parts = [
        f"处理 {stats['files']} 个文件",
        f"删除空行 {stats['removed_rows']} 行",
        f"去重 {stats['removed_dups']} 行",
        f"规范化日期列 {stats['date_cols']} 个",
    ]
    if stats["date_failures"]:
        parts.append(f"日期识别失败 {stats['date_failures']} 行")
    if stats["numbers"]:
        parts.append(f"转换数字 {stats['numbers']} 个")
    if stats.get("phones"):
        parts.append(f"规范化手机号列 {stats['phones']} 个")
    if stats["hyperlinks"] or stats["comments"]:
        extras = []
        if stats["hyperlinks"]:
            extras.append(f"超链接 {stats['hyperlinks']} 个")
        if stats["comments"]:
            extras.append(f"批注 {stats['comments']} 个")
        parts.append("清除" + "、".join(extras))

    log("✔ 格式统一完成：" + "，".join(parts)
        + f" → {quote_path(output_dir)}", "success")
    return stats
