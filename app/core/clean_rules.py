"""通用原子清洗配置引擎。

把「清洗动作」拆成可注册、可组合的原子规则：

- 全局规则：作用于整张表（空行、空列、去重、全表数字/日期统一等）；
- 单列绑定规则：用户指定列 + 规则（手机号、金额、日期、文本空格等）。

本模块只负责规则注册、执行计划、序列化和输出格式，不修改合并、拆分、
导出、日志、文件占用等既有流程。
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd

from .errors import FriendlyError


# --------------------------------------------------------------------------- #
# 规则注册表
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class AtomicRule:
    """一条原子清洗规则。"""

    key: str
    label: str
    scope: str  # "global" / "column"
    description: str = ""
    number_format: Optional[str] = None
    alignment: Optional[str] = None
    convert_date: bool = False


GLOBAL_RULE_ORDER = [
    "remove_empty_rows",
    "remove_empty_cols",
    "strip_text",
    "normalize_numbers",
    "drop_duplicates",
    "normalize_dates",
    "clear_hyperlinks",
    "clear_comments",
]

COLUMN_RULE_ORDER = [
    "column_strip_text",
    "phone",
    "amount",
    "date",
    "text",
]


RULE_REGISTRY: Dict[str, AtomicRule] = {}


def _register(rule: AtomicRule) -> None:
    RULE_REGISTRY[rule.key] = rule


_register(AtomicRule(
    "remove_empty_rows", "清除完全为空的行", "global",
    "删除所有单元格都为空的行"))
_register(AtomicRule(
    "remove_empty_cols", "清除完全为空的列", "global",
    "删除所有单元格都为空的列"))
_register(AtomicRule(
    "strip_text", "去除文本首尾空格", "global",
    "对整张表的文本单元格去除首尾空格"))
_register(AtomicRule(
    "normalize_numbers", "数字统一", "global",
    "去千分位、货币符号，文本数字转数值；保留编号/手机号"))
_register(AtomicRule(
    "drop_duplicates", "删除重复行", "global",
    "按全部列或指定列去重"))
_register(AtomicRule(
    "normalize_dates", "日期统一", "global",
    "自动识别日期列并统一格式；识别失败保留原值并记录日志"))
_register(AtomicRule(
    "clear_hyperlinks", "清除超链接", "global",
    "输出纯数据，不保留单元格超链接"))
_register(AtomicRule(
    "clear_comments", "清除批注", "global",
    "输出纯数据，不保留单元格批注"))

_register(AtomicRule(
    "column_strip_text", "去除文本首尾空格", "column",
    "只处理绑定列中的文本单元格",
    number_format="@", alignment="left"))
_register(AtomicRule(
    "phone", "手机号标准化", "column",
    "全角转半角，去除空格、横杠、括号，保留前导零；按文本写入",
    number_format="@", alignment="center"))
_register(AtomicRule(
    "amount", "金额转数字", "column",
    "去千分位/货币符号并转数值，按金额格式写入",
    number_format="#,##0.00", alignment="right"))
_register(AtomicRule(
    "date", "日期统一", "column",
    "按目标日期格式统一，并在 Excel 中写成日期格式",
    number_format="yyyy-mm-dd", alignment="center",
    convert_date=True))
_register(AtomicRule(
    "text", "文本格式（@）", "column",
    "不改变内容，只把绑定列按文本格式、左对齐写入",
    number_format="@", alignment="left"))


GLOBAL_RULES = {key: RULE_REGISTRY[key] for key in GLOBAL_RULE_ORDER}
COLUMN_RULES = {key: RULE_REGISTRY[key] for key in COLUMN_RULE_ORDER}


def get_rule(key: str) -> Optional[AtomicRule]:
    return RULE_REGISTRY.get(str(key or "").strip())


def normalize_global_rules(rules: Optional[Iterable[str]]) -> List[str]:
    """过滤未知规则，并按固定的全局执行顺序返回。"""
    if rules is None:
        return []
    selected = {str(item).strip() for item in rules if str(item).strip()}
    return [key for key in GLOBAL_RULE_ORDER if key in selected]


def legacy_global_rules(remove_empty_rows: bool,
                        remove_empty_cols: bool,
                        strip_text: bool,
                        clear_hyperlinks: bool,
                        clear_comments: bool,
                        normalize_numbers: bool,
                        drop_duplicates: bool,
                        normalize_date: bool) -> List[str]:
    """把旧版布尔参数翻译成全局规则键，保证旧调用方式可用。"""
    mapping = [
        ("remove_empty_rows", remove_empty_rows),
        ("remove_empty_cols", remove_empty_cols),
        ("strip_text", strip_text),
        ("normalize_numbers", normalize_numbers),
        ("drop_duplicates", drop_duplicates),
        ("normalize_dates", normalize_date),
        ("clear_hyperlinks", clear_hyperlinks),
        ("clear_comments", clear_comments),
    ]
    return normalize_global_rules([key for key, enabled in mapping if enabled])


@dataclass
class ColumnBinding:
    """一条「列 + 原子规则」绑定。"""

    column: str
    rule: str
    options: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column": self.column,
            "rule": self.rule,
            **({"options": dict(self.options)} if self.options else {}),
        }


def normalize_column_bindings(value: Any) -> List[ColumnBinding]:
    """把方案/UI 中的绑定数据整理成稳定对象；未知规则会被忽略。"""
    if not isinstance(value, (list, tuple)):
        return []
    bindings: List[ColumnBinding] = []
    for item in value:
        if isinstance(item, ColumnBinding):
            column, rule, options = item.column, item.rule, item.options
        elif isinstance(item, Mapping):
            column = str(item.get("column", "") or "").strip()
            rule = str(item.get("rule", "") or "").strip()
            options = item.get("options", {})
        else:
            continue
        if not column or rule not in COLUMN_RULES:
            continue
        bindings.append(ColumnBinding(
            column=column, rule=rule,
            options=dict(options) if isinstance(options, Mapping) else {}))
    return bindings


def column_bindings_to_dict(
        bindings: Sequence[ColumnBinding]) -> List[Dict[str, Any]]:
    return [binding.to_dict() for binding in bindings]


# --------------------------------------------------------------------------- #
# 旧清洗函数的薄包装：直接复用 formatter 里的算法，不重写逻辑
# --------------------------------------------------------------------------- #
def _formatter_module():
    # 延迟导入，避免 formatter -> clean_rules -> formatter 的循环导入。
    from . import formatter
    return formatter


def valid_date_format(fmt: str) -> bool:
    return bool(_formatter_module()._valid_date_format(fmt))


def normalize_amount_series(series: pd.Series):
    return _formatter_module()._normalize_number_series(series)


def normalize_date_series(series: pd.Series, fmt: str,
                          recognize_chinese: bool):
    return _formatter_module()._normalize_date_series(
        series, fmt, recognize_chinese)


def looks_like_dates(series: pd.Series, recognize_chinese: bool) -> bool:
    return bool(_formatter_module()._looks_like_dates(
        series, recognize_chinese))


def log_date_failures(log, name: str, sheet_name: str,
                      column: str, failures) -> None:
    _formatter_module()._log_date_failures(
        log, name, sheet_name, column, failures)


def _is_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and not value.strip()


# --------------------------------------------------------------------------- #
# 原子清洗函数
# --------------------------------------------------------------------------- #
def normalize_phone_value(value):
    """手机号原子规则：沿用「保留文本、不转数字」的策略。"""
    if _is_blank(value):
        return value
    text = unicodedata.normalize("NFKC", str(value)).strip()
    # 只去掉常见的分隔符，不动数字本身；+86 等前缀保留。
    text = re.sub(r"[\s\-–—()（）]+", "", text)
    return text


def _strip_series(series: pd.Series) -> pd.Series:
    return series.map(lambda value: value.strip()
                      if isinstance(value, str) else value)


def apply_global_rules(frame: pd.DataFrame,
                       rule_keys: Sequence[str],
                       *,
                       dedup_columns: Sequence[str] = (),
                       date_columns: Sequence[str] = (),
                       date_format: str = "%Y-%m-%d",
                       recognize_chinese_dates: bool = True,
                       file_name: str = "",
                       sheet_name: str = "",
                       log=None,
                       stats: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """按固定顺序执行全局规则。"""
    selected = set(normalize_global_rules(rule_keys))
    if not selected:
        return frame

    stats = stats if stats is not None else {}

    if "remove_empty_rows" in selected:
        frame = frame.dropna(how="all")

    if "remove_empty_cols" in selected:
        frame = frame.dropna(axis=1, how="all")

    if "strip_text" in selected:
        for column in frame.columns:
            if (pd.api.types.is_object_dtype(frame[column])
                    or pd.api.types.is_string_dtype(frame[column])):
                frame[column] = _strip_series(frame[column])

    if "normalize_numbers" in selected:
        for column in frame.columns:
            normalized, count = normalize_amount_series(frame[column])
            if count:
                frame[column] = normalized
                stats["numbers"] = stats.get("numbers", 0) + count

    if "drop_duplicates" in selected:
        subset = [c for c in (dedup_columns or [])
                  if c in frame.columns] or None
        before_dup = len(frame)
        frame = frame.drop_duplicates(subset=subset, keep="first")
        stats["removed_dups"] = (
            stats.get("removed_dups", 0) + before_dup - len(frame))

    if "normalize_dates" in selected:
        columns = [c for c in (date_columns or []) if c in frame.columns]
        if not columns:
            columns = [c for c in frame.columns
                       if looks_like_dates(frame[c], recognize_chinese_dates)]
        for column in columns:
            frame[column], failures = normalize_date_series(
                frame[column], date_format, recognize_chinese_dates)
            stats["date_cols"] = stats.get("date_cols", 0) + 1
            if failures:
                stats["date_failures"] = (
                    stats.get("date_failures", 0) + len(failures))
                if log:
                    log_date_failures(
                        log, file_name, sheet_name, column, failures)

    # clear_hyperlinks / clear_comments 不改变 DataFrame，
    # 输出纯数据时自然不保留；数量统计由 formatter 负责。
    return frame


def apply_column_bindings(frame: pd.DataFrame,
                          bindings: Sequence[ColumnBinding],
                          *,
                          date_format: str = "%Y-%m-%d",
                          recognize_chinese_dates: bool = True,
                          file_name: str = "",
                          sheet_name: str = "",
                          log=None,
                          stats: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    """在全局规则之后，按用户顺序执行单列绑定规则。"""
    stats = stats if stats is not None else {}
    for binding in normalize_column_bindings(bindings):
        rule = COLUMN_RULES.get(binding.rule)
        if rule is None:
            continue
        if binding.column not in frame.columns:
            if log:
                log(f"⚠ {file_name} [{sheet_name}] 缺少绑定列 "
                    f"“{binding.column}”，已跳过规则“{rule.label}”", "warn")
            continue

        column = binding.column
        if binding.rule == "column_strip_text":
            frame[column] = _strip_series(frame[column])
        elif binding.rule == "phone":
            frame[column] = frame[column].map(normalize_phone_value)
            stats["phones"] = stats.get("phones", 0) + 1
        elif binding.rule == "amount":
            normalized, count = normalize_amount_series(frame[column])
            if count:
                frame[column] = normalized
                stats["numbers"] = stats.get("numbers", 0) + count
        elif binding.rule == "date":
            frame[column], failures = normalize_date_series(
                frame[column], date_format, recognize_chinese_dates)
            stats["date_cols"] = stats.get("date_cols", 0) + 1
            if failures:
                stats["date_failures"] = (
                    stats.get("date_failures", 0) + len(failures))
                if log:
                    log_date_failures(
                        log, file_name, sheet_name, column, failures)
        elif binding.rule == "text":
            # 只影响写出格式，不改变数据内容。
            pass
    return frame


# --------------------------------------------------------------------------- #
# 写入后的格式套用
# --------------------------------------------------------------------------- #
def python_date_to_excel(fmt: str) -> str:
    """把常见的 Python strftime 格式转换为 Excel 数字格式。"""
    text = str(fmt or "%Y-%m-%d")
    replacements = (
        ("%Y", "yyyy"), ("%y", "yy"),
        ("%m", "mm"), ("%d", "dd"),
        ("%H", "hh"), ("%M", "mm"), ("%S", "ss"),
    )
    for source, target in replacements:
        text = text.replace(source, target)
    return text or "yyyy-mm-dd"


def _apply_binding_formats(path: str,
                           bindings: Sequence[ColumnBinding],
                           date_format: str) -> None:
    if not bindings:
        return
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import Alignment
    except ImportError:
        return

    workbook = load_workbook(path)
    for worksheet in workbook.worksheets:
        header_map = {}
        for cell in worksheet[1]:
            if cell.value is not None:
                header_map[str(cell.value).strip()] = cell.column

        for binding in normalize_column_bindings(bindings):
            rule = COLUMN_RULES.get(binding.rule)
            column_index = header_map.get(binding.column)
            if rule is None or column_index is None:
                continue

            number_format = rule.number_format
            if binding.rule == "date":
                number_format = python_date_to_excel(date_format)

            for row_index in range(2, worksheet.max_row + 1):
                cell = worksheet.cell(row_index, column_index)
                if rule.convert_date and isinstance(cell.value, str):
                    parsed = pd.to_datetime(cell.value, errors="coerce")
                    if not pd.isna(parsed):
                        cell.value = parsed.to_pydatetime()
                if number_format:
                    cell.number_format = number_format
                if rule.alignment:
                    cell.alignment = Alignment(
                        horizontal=rule.alignment, vertical="center",
                        wrap_text=bool(cell.alignment.wrap_text))
    workbook.save(path)


def write_clean_output(frames: Mapping[str, pd.DataFrame],
                       path: str,
                       bindings: Sequence[ColumnBinding],
                       *,
                       date_format: str = "%Y-%m-%d") -> None:
    """沿用现有导出函数写出，再按绑定规则补充数字格式/对齐。"""
    from .excel_engine import write_dataframe, write_workbook

    if len(frames) == 1:
        sheet_name, frame = next(iter(frames.items()))
        write_dataframe(frame, path, sheet_name=sheet_name)
    else:
        write_workbook(frames, path)
    _apply_binding_formats(path, bindings, date_format)


# --------------------------------------------------------------------------- #
# 方案 JSON：页面级保存/加载与主方案共用数据结构
# --------------------------------------------------------------------------- #
def clean_plan_data(global_rules: Sequence[str],
                    bindings: Sequence[ColumnBinding],
                    options: Optional[Mapping[str, Any]] = None
                    ) -> Dict[str, Any]:
    return {
        "version": 1,
        "global_rules": normalize_global_rules(global_rules),
        "column_bindings": column_bindings_to_dict(
            normalize_column_bindings(bindings)),
        "options": dict(options or {}),
    }


def save_clean_plan(path: str,
                    global_rules: Sequence[str],
                    bindings: Sequence[ColumnBinding],
                    options: Optional[Mapping[str, Any]] = None) -> None:
    """原子写入页面级清洗规则 JSON。"""
    data = clean_plan_data(global_rules, bindings, options)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def load_clean_plan(path: str) -> Dict[str, Any]:
    """读取页面级清洗规则 JSON，返回规范化后的数据。"""
    try:
        with open(path, "r", encoding="utf-8-sig") as fp:
            data = json.load(fp)
    except json.JSONDecodeError as exc:
        raise FriendlyError(
            "清洗规则文件格式不正确",
            detail=f"JSON 解析失败：{exc.msg}（第 {exc.lineno} 行）。",
            hint="请重新保存规则文件，或选择其他 JSON 文件。",
        ) from exc

    if not isinstance(data, dict):
        raise FriendlyError(
            "清洗规则文件格式不正确",
            detail="规则文件的根节点必须是 JSON 对象。",
            hint="请重新保存规则文件。",
        )
    options = data.get("options")
    return {
        "global_rules": normalize_global_rules(data.get("global_rules", [])),
        "column_bindings": normalize_column_bindings(
            data.get("column_bindings", [])),
        "options": dict(options) if isinstance(options, Mapping) else {},
    }
