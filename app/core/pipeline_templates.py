"""流水线模板库：内置模板 + 用户保存在 config 里的模板。

内置模板直接写在代码里，随程序升级；用户模板保存为
``config/pipeline_templates.json``，只保存节点 / 连线 / 参数，不保存
任何本地文件路径或表头预览数据。
"""
from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from app.config import PIPELINE_TEMPLATE_FILE

from .errors import FriendlyError, record_exception
from .pipeline import (NODE_CLEAN, NODE_FILE, NODE_MERGE, NODE_OUTPUT,
                       NODE_SPLIT, parse_graph, strip_graph_for_template)

_SCHEMA_VERSION = 1
_LAST_LOAD_ERROR = ""


def _file_node(node_id: str, x: float, y: float) -> Dict[str, Any]:
    return {
        "id": node_id, "type": NODE_FILE,
        "position": {"x": x, "y": y},
        "data": {"path": "", "name": "", "columns": [], "rows": [],
                 "sheets": [], "loading": False, "error": ""},
    }


def _merge_node(node_id: str, x: float, y: float) -> Dict[str, Any]:
    return {
        "id": node_id, "type": NODE_MERGE,
        "position": {"x": x, "y": y},
        "data": {
            "addSource": True, "sourceColumn": "来源文件",
            "sheetColumn": "来源工作表", "allSheets": True,
            "alignment": "union", "ignoreEmpty": True,
            "sortColumns": "", "sortAscending": True,
        },
    }


def _clean_node(node_id: str, x: float, y: float) -> Dict[str, Any]:
    return {
        "id": node_id, "type": NODE_CLEAN,
        "position": {"x": x, "y": y},
        "data": {
            "removeEmptyRows": True, "removeEmptyCols": True,
            "stripText": True, "normalizeNumbers": True,
            "normalizeDates": True, "dropDuplicates": False,
            "dateFormat": "%Y-%m-%d",
        },
    }


def _output_node(node_id: str, x: float, y: float,
                 file_name: str) -> Dict[str, Any]:
    return {
        "id": node_id, "type": NODE_OUTPUT,
        "position": {"x": x, "y": y},
        "data": {"fileName": file_name, "outputDir": "", "autoRename": True},
    }


def _edge(source: str, target: str) -> Dict[str, str]:
    return {"id": f"e-{source}-{target}", "source": source, "target": target}


def _builtin_merge() -> Dict[str, Any]:
    nodes = [
        _file_node("file-1", 40, 30),
        _file_node("file-2", 40, 250),
        _file_node("file-3", 40, 470),
        _merge_node("merge-1", 380, 250),
        _output_node("output-1", 720, 275, "合并结果_{日期}.xlsx"),
    ]
    edges = [
        _edge("file-1", "merge-1"),
        _edge("file-2", "merge-1"),
        _edge("file-3", "merge-1"),
        _edge("merge-1", "output-1"),
    ]
    return {"version": 1, "nodes": nodes, "edges": edges}


def _builtin_merge_clean() -> Dict[str, Any]:
    nodes = [
        _file_node("file-1", 30, 30),
        _file_node("file-2", 30, 250),
        _file_node("file-3", 30, 470),
        _merge_node("merge-1", 350, 250),
        _clean_node("clean-1", 640, 250),
        _output_node("output-1", 930, 275, "清洗结果_{日期}.xlsx"),
    ]
    edges = [
        _edge("file-1", "merge-1"),
        _edge("file-2", "merge-1"),
        _edge("file-3", "merge-1"),
        _edge("merge-1", "clean-1"),
        _edge("clean-1", "output-1"),
    ]
    return {"version": 1, "nodes": nodes, "edges": edges}


_BUILTINS = [
    {
        "id": "builtin_merge",
        "name": "一键合并",
        "description": "3 个文件节点 → 合并（带来源列）→ 输出。把 Excel 拖到左侧文件卡片即可运行。",
        "builtin": True,
        "graph": _builtin_merge(),
    },
    {
        "id": "builtin_merge_clean",
        "name": "合并 + 清洗",
        "description": "多文件合并后删除空行空列、统一数字与日期格式，再写出结果。",
        "builtin": True,
        "graph": _builtin_merge_clean(),
    },
]


def builtin_templates() -> List[Dict[str, Any]]:
    return copy.deepcopy(_BUILTINS)


def template_file_path() -> str:
    return PIPELINE_TEMPLATE_FILE


def get_last_load_error() -> str:
    return _LAST_LOAD_ERROR


def _read_store() -> Dict[str, Any]:
    global _LAST_LOAD_ERROR
    _LAST_LOAD_ERROR = ""
    path = template_file_path()
    if not os.path.exists(path):
        return {"version": _SCHEMA_VERSION, "templates": []}
    try:
        with open(path, "r", encoding="utf-8-sig") as fp:
            data = json.load(fp)
    except json.JSONDecodeError as exc:
        _LAST_LOAD_ERROR = f"模板文件 JSON 解析失败：第 {exc.lineno} 行 {exc.msg}"
        record_exception(exc, "读取流水线模板")
        return {"version": _SCHEMA_VERSION, "templates": []}
    except OSError as exc:
        _LAST_LOAD_ERROR = f"无法读取模板文件：{exc}"
        record_exception(exc, "读取流水线模板")
        return {"version": _SCHEMA_VERSION, "templates": []}
    if not isinstance(data, Mapping) or not isinstance(data.get("templates"), list):
        _LAST_LOAD_ERROR = "模板文件格式不正确，已忽略其中的用户模板。"
        return {"version": _SCHEMA_VERSION, "templates": []}
    return {"version": _SCHEMA_VERSION, "templates": list(data["templates"])}


def _write_store(templates: List[Dict[str, Any]]) -> None:
    path = template_file_path()
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    data = {"version": _SCHEMA_VERSION, "templates": templates}
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


def _public_template(record: Mapping[str, Any], builtin: bool) -> Dict[str, Any]:
    return {
        "id": str(record.get("id", "")),
        "name": str(record.get("name", "")) or "未命名模板",
        "description": str(record.get("description", "")),
        "builtin": bool(builtin),
        "createdAt": str(record.get("createdAt", "")),
        "graph": copy.deepcopy(record.get("graph") or {}),
    }


def list_templates() -> List[Dict[str, Any]]:
    """内置模板在前，用户模板按创建时间倒序。"""
    global _LAST_LOAD_ERROR
    store = _read_store()
    users: List[Dict[str, Any]] = []
    invalid = 0
    for record in store.get("templates", []):
        if not isinstance(record, Mapping):
            continue
        template_id = str(record.get("id", ""))
        graph = record.get("graph")
        if not template_id or not isinstance(graph, Mapping):
            invalid += 1
            continue
        try:
            parse_graph(graph)
        except Exception:  # noqa: BLE001
            invalid += 1
            continue
        users.append(_public_template(record, builtin=False))
    if invalid and not _LAST_LOAD_ERROR:
        _LAST_LOAD_ERROR = f"有 {invalid} 个用户模板结构不完整，已跳过。"
    users.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return [copy.deepcopy(item) for item in _BUILTINS] + users


def _describe_graph(graph: Mapping[str, Any]) -> str:
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else []
    if not isinstance(nodes, list):
        return ""
    counts = {NODE_FILE: 0, NODE_MERGE: 0, NODE_CLEAN: 0,
              NODE_SPLIT: 0, NODE_OUTPUT: 0}
    for node in nodes:
        if isinstance(node, Mapping):
            node_type = str(node.get("type", ""))
            if node_type in counts:
                counts[node_type] += 1
    steps = []
    if counts[NODE_MERGE]:
        steps.append("合并")
    if counts[NODE_CLEAN]:
        steps.append("清洗")
    if counts[NODE_SPLIT]:
        steps.append("拆分")
    if counts[NODE_OUTPUT]:
        steps.append("输出")
    prefix = f"{counts[NODE_FILE]} 个文件节点" if counts[NODE_FILE] else ""
    if prefix and steps:
        return prefix + " · " + " → ".join(steps)
    return prefix or " → ".join(steps)


def save_user_template(name: str,
                       graph: Mapping[str, Any],
                       description: str = "") -> Dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise FriendlyError("请填写模板名称", hint="例如「销售日报合并」。")
    if len(clean_name) > 40:
        raise FriendlyError("模板名称太长", detail="最多 40 个字符。")
    if any(str(item.get("name", "")).strip() == clean_name for item in _BUILTINS):
        raise FriendlyError(
            "模板名称与内置模板重复",
            detail=f"已经有一个内置模板叫「{clean_name}」。",
            hint="请换一个名称，例如「我的" + clean_name + "」。",
        )

    parse_graph(graph)  # 结构校验（允许还没接完整，但不允许环 / 非法端口）
    template_graph = strip_graph_for_template(graph)
    clean_description = str(description or "").strip() or _describe_graph(template_graph)

    store = _read_store()
    records = [dict(item) for item in store.get("templates", [])
               if isinstance(item, Mapping)]
    now = datetime.now().isoformat(timespec="seconds")
    existing: Optional[Dict[str, Any]] = None
    for record in records:
        if str(record.get("name", "")).strip() == clean_name:
            existing = record
            break
    if existing is None:
        existing = {
            "id": f"user_{uuid.uuid4().hex[:12]}",
            "createdAt": now,
        }
        records.append(existing)
    existing.update({
        "name": clean_name,
        "description": clean_description,
        "updatedAt": now,
        "graph": template_graph,
    })
    if "createdAt" not in existing:
        existing["createdAt"] = now
    _write_store(records)
    return _public_template(existing, builtin=False)


def delete_user_template(template_id: str) -> bool:
    target = str(template_id or "").strip()
    if not target:
        return False
    store = _read_store()
    records = [dict(item) for item in store.get("templates", [])
               if isinstance(item, Mapping)]
    kept = [item for item in records if str(item.get("id", "")) != target]
    if len(kept) == len(records):
        return False
    _write_store(kept)
    return True


def get_template(template_id: str) -> Optional[Dict[str, Any]]:
    target = str(template_id or "").strip()
    if not target:
        return None
    for template in list_templates():
        if template.get("id") == target:
            return template
    return None
