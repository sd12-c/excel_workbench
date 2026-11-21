"""核心层通用工具。"""
import os
import re
from typing import List


def noop_log(message: str, level: str = "info") -> None:
    """默认空日志回调。"""


def noop_progress(done: int, total: int) -> None:
    """默认空进度回调。"""


def normalize_path(path: str) -> str:
    """统一路径分隔符，清理粘贴时带的引号和首尾空格。

    例如 ``"E:/python 项目/out/结果.xlsx"`` → ``E:\\python 项目\\out\\结果.xlsx``。
    UNC 路径（``\\\\server\\share``）由 ``os.path.normpath`` 原样保留。
    """
    text = str(path or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    if not text:
        return ""
    if os.name == "nt":
        text = text.replace("/", "\\")
    return os.path.normpath(text)


def quote_path(path: str) -> str:
    """用双引号包裹路径，方便从运行日志中复制。"""
    text = normalize_path(path)
    return f'"{text}"' if text else '""'


def safe_sheet_name(name: str) -> str:
    """把任意文本转换为合法的 Excel 工作表名（<=31 字符）。"""
    text = str(name)
    for ch in ':\\/?*[]':
        text = text.replace(ch, "_")
    text = text.strip() or "Sheet"
    return text[:31]


def sanitize_filename(name: str, max_len: int = 120) -> str:
    """清理非法文件名字符。"""
    text = str(name)
    for ch in '<>:"/\\|?*\n\r\t':
        text = text.replace(ch, "_")
    text = text.strip().strip(".")
    if not text:
        text = "未命名"
    return text[:max_len]


def unique_path(path: str) -> str:
    """若文件已存在，自动追加序号，避免覆盖。"""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    index = 1
    while True:
        candidate = f"{base}_{index}{ext}"
        if not os.path.exists(candidate):
            return candidate
        index += 1


def split_csv_line(text: str) -> List[str]:
    """把 "A,B，C" 拆成干净的列名列表（支持中英文逗号）。"""
    if not text:
        return []
    parts = re.split(r"[,，;；\n]", text)
    return [p.strip() for p in parts if p.strip()]