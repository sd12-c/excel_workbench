"""方案文件读写与字段安全取值。"""
import json
import os
from typing import Any, Dict

from app.core.errors import FriendlyError

SCHEMA_VERSION = 1


def save_scheme_file(path: str, data: Dict[str, Any]) -> None:
    """原子写入方案 JSON，避免写入中途留下半个文件。"""
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


def load_scheme_file(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8-sig") as fp:
            data = json.load(fp)
    except json.JSONDecodeError as exc:
        raise FriendlyError(
            "方案文件格式不正确",
            detail=f"JSON 解析失败：{exc.msg}（第 {exc.lineno} 行）。",
            hint="请重新保存方案，或选择其他方案文件。",
        ) from exc

    if not isinstance(data, dict):
        raise FriendlyError(
            "方案文件格式不正确",
            detail="方案文件的根节点必须是一个 JSON 对象。",
            hint="请重新保存方案，或选择其他方案文件。",
        )
    pages = data.get("pages")
    if pages is not None and not isinstance(pages, dict):
        raise FriendlyError(
            "方案文件格式不正确",
            detail="方案文件中的 pages 字段必须是对象。",
            hint="请重新保存方案，或选择其他方案文件。",
        )
    return data


def scheme_bool(data: Dict[str, Any], key: str, default: bool) -> bool:
    value = data.get(key, default)
    return value if isinstance(value, bool) else default


def scheme_str(data: Dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key, default)
    return value if isinstance(value, str) else default


def scheme_int(data: Dict[str, Any], key: str, default: int = 0) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value
