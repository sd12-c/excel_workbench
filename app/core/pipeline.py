"""流水线画布的业务编排层。

这一层完全不依赖 Qt / WebView，只做三件事：

1. 解析前端传来的流程图 JSON，校验节点与连线（拓扑、端口、环）；
2. 按拓扑顺序依次调用项目里已有的合并 / 清洗 / 拆分 / 导出函数；
3. 通过回调把「节点开始、节点完成、实时行数、运行日志」交给界面层。

前端只负责画布交互，所有 Excel / pandas 处理仍然复用原有实现。
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from .clean_rules import (apply_column_bindings, apply_global_rules,
                          normalize_global_rules, valid_date_format)
from .common import normalize_path, sanitize_filename, unique_path
from .errors import FriendlyError, explain, record_exception
from .excel_engine import EXCEL_EXTENSIONS, read_workbook, write_dataframe, write_workbook
from .merger import (ALIGNMENT_INTERSECTION, ALIGNMENT_UNION, merge_files)
from .preview import preview_frame
from .splitter import split_by_column, validate_filename_template

# --------------------------------------------------------------------------- #
# 节点类型
# --------------------------------------------------------------------------- #
NODE_FILE = "file"
NODE_MERGE = "merge"
NODE_CLEAN = "clean"
NODE_SPLIT = "split"
NODE_OUTPUT = "output"

SUPPORTED_NODE_TYPES = {NODE_FILE, NODE_MERGE, NODE_CLEAN, NODE_SPLIT, NODE_OUTPUT}
TERMINAL_NODE_TYPES = {NODE_SPLIT, NODE_OUTPUT}
DATA_NODE_TYPES = {NODE_FILE, NODE_MERGE, NODE_CLEAN}

NODE_LABELS = {
    NODE_FILE: "文件节点",
    NODE_MERGE: "合并节点",
    NODE_CLEAN: "清洗节点",
    NODE_SPLIT: "拆分节点",
    NODE_OUTPUT: "输出节点",
}

DEFAULT_OUTPUT_NAME = "流水线结果_{时间戳}.xlsx"
DEFAULT_SPLIT_TEMPLATE = "{分组列值}.xlsx"


class PipelineCancelled(Exception):
    """用户点击停止；由执行引擎在安全点抛出。"""


class PipelineNodeError(FriendlyError):
    """某个节点执行失败，携带节点 id，方便前端高亮。"""

    def __init__(self, node_id: str, node_label: str, cause: BaseException) -> None:
        info = explain(cause)
        title = info.title or "节点执行失败"
        if node_label and not title.startswith(node_label):
            title = f"{node_label}失败：{title}"
        super().__init__(title, detail=info.detail, hint=info.hint)
        self.node_id = str(node_id or "")
        self.node_label = str(node_label or "")
        self.cause = cause


# --------------------------------------------------------------------------- #
# 图结构
# --------------------------------------------------------------------------- #
@dataclass
class PipelineNode:
    id: str
    type: str
    position: Tuple[float, float]
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return NODE_LABELS.get(self.type, self.type)


@dataclass
class ParsedGraph:
    nodes: Dict[str, PipelineNode]
    edges: List[Tuple[str, str]]
    inputs: Dict[str, List[str]]
    outputs: Dict[str, List[str]]
    order: List[str]
    terminals: List[str]
    reachable: List[str]
    ignored: List[str]

    @property
    def node_count(self) -> int:
        return len(self.nodes)


@dataclass
class RunContext:
    graph: ParsedGraph
    default_output_dir: str
    temp_dir: str
    emit: Callable[[str, Dict[str, Any]], None]
    log: Callable[[str, str], None]
    progress: Callable[[int, int], None]
    is_cancelled: Callable[[], bool]
    results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    frames: Dict[str, Dict[str, pd.DataFrame]] = field(default_factory=dict)
    output_paths: List[Dict[str, str]] = field(default_factory=list)

    def check_cancelled(self) -> None:
        if self.is_cancelled():
            raise PipelineCancelled()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
    return default


def _as_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_position(value: Any) -> Tuple[float, float]:
    data = _as_mapping(value)
    try:
        x = float(data.get("x", 0) or 0)
    except (TypeError, ValueError):
        x = 0.0
    try:
        y = float(data.get("y", 0) or 0)
    except (TypeError, ValueError):
        y = 0.0
    return x, y


def parse_graph(graph: Mapping[str, Any]) -> ParsedGraph:
    """解析并做结构校验；允许节点尚未连完整（保存模板时用）。"""
    if not isinstance(graph, Mapping):
        raise FriendlyError("流程图格式不正确", detail="根节点必须是 JSON 对象。")
    raw_nodes = graph.get("nodes")
    raw_edges = graph.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise FriendlyError("画布上还没有节点", hint="请把 Excel 文件拖入画布，或载入一个模板。")
    if raw_edges is None:
        raw_edges = []
    if not isinstance(raw_edges, list):
        raise FriendlyError("流程图格式不正确", detail="edges 字段必须是数组。")

    nodes: Dict[str, PipelineNode] = {}
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise FriendlyError("流程图格式不正确", detail="nodes 中存在非对象节点。")
        node_id = _as_text(raw.get("id"))
        node_type = _as_text(raw.get("type"))
        if not node_id:
            raise FriendlyError("流程图格式不正确", detail="存在缺少 id 的节点。")
        if node_id in nodes:
            raise FriendlyError("流程图格式不正确", detail=f"节点 id 重复：{node_id}")
        if node_type not in SUPPORTED_NODE_TYPES:
            raise FriendlyError(
                "存在不支持的节点类型",
                detail=f"节点 {node_id} 的类型是「{node_type or '空'}」。",
                hint="请删除该节点后重新添加。",
            )
        data = dict(_as_mapping(raw.get("data")))
        nodes[node_id] = PipelineNode(
            id=node_id, type=node_type,
            position=_as_position(raw.get("position")), data=data)

    edges: List[Tuple[str, str]] = []
    inputs: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    outputs: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    seen_edges = set()
    for raw in raw_edges:
        if not isinstance(raw, Mapping):
            raise FriendlyError("流程图格式不正确", detail="edges 中存在非对象连线。")
        source = _as_text(raw.get("source"))
        target = _as_text(raw.get("target"))
        if not source or not target:
            raise FriendlyError("流程图格式不正确", detail="存在缺少起点或终点的连线。")
        if source not in nodes or target not in nodes:
            raise FriendlyError(
                "流程图里存在指向不存在节点的连线",
                detail=f"{source or '空'} → {target or '空'}",
                hint="请删除这条连线后重新连接。",
            )
        if source == target:
            raise FriendlyError("节点不能连到自己", detail=f"{nodes[source].label}存在自环连线。")
        key = (source, target)
        if key in seen_edges:
            continue
        seen_edges.add(key)

        source_node = nodes[source]
        target_node = nodes[target]
        if source_node.type in TERMINAL_NODE_TYPES:
            raise FriendlyError(
                f"{source_node.label}不能继续向下连接",
                detail=f"{source_node.label}已经是管线终点。",
                hint="请把输出 / 拆分节点放在管线末端。",
            )
        if target_node.type == NODE_FILE:
            raise FriendlyError("文件节点不能作为连线终点", detail="文件节点是管线的起点。")
        if target_node.type == NODE_MERGE and source_node.type != NODE_FILE:
            raise FriendlyError(
                "合并节点的输入必须直接来自文件节点",
                detail=f"{nodes[source].label} → {nodes[target].label} 不是合法的合并输入。",
                hint="请把 Excel 文件节点直接连到合并节点；合并后的数据再连到清洗 / 输出。",
            )
        edges.append(key)
        inputs[target].append(source)
        outputs[source].append(target)

    for node in nodes.values():
        incoming = len(inputs[node.id])
        if node.type == NODE_FILE and incoming:
            raise FriendlyError("文件节点不能有输入", detail=f"{node.label}只能作为起点。")
        if node.type in {NODE_CLEAN, NODE_SPLIT, NODE_OUTPUT} and incoming > 1:
            raise FriendlyError(
                f"{node.label}只能接收一个输入",
                detail=f"{node.label}当前有 {incoming} 条输入连线。",
                hint="请只保留一条输入连线。",
            )
        if node.type == NODE_CLEAN and not outputs[node.id]:
            # 允许暂时没接输出，运行时若不可达会被忽略；这里不报错。
            pass

    order = _topological_order(nodes, edges)
    terminals = [node_id for node_id, node in nodes.items()
                 if node.type in TERMINAL_NODE_TYPES]
    reachable = _reachable_from_terminals(terminals, inputs)
    ignored = [node_id for node_id in nodes if node_id not in reachable]
    return ParsedGraph(nodes=nodes, edges=edges, inputs=inputs, outputs=outputs,
                       order=order, terminals=terminals, reachable=reachable,
                       ignored=ignored)


def _topological_order(nodes: Mapping[str, PipelineNode],
                       edges: Sequence[Tuple[str, str]]) -> List[str]:
    indegree = {node_id: 0 for node_id in nodes}
    adjacency: Dict[str, List[str]] = {node_id: [] for node_id in nodes}
    for source, target in edges:
        adjacency[source].append(target)
        indegree[target] += 1

    ready = [node_id for node_id, count in indegree.items() if count == 0]
    order: List[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for target in adjacency[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)

    if len(order) != len(nodes):
        remaining = [node_id for node_id in nodes if node_id not in set(order)]
        labels = "、".join(nodes[node_id].label for node_id in remaining[:6])
        raise FriendlyError(
            "流程图里存在循环连线",
            detail=f"涉及节点：{labels}",
            hint="请断开形成环的连线；数据只能单向流动。",
        )
    return order


def _reachable_from_terminals(terminals: Sequence[str],
                              inputs: Mapping[str, List[str]]) -> List[str]:
    seen = set()
    stack = list(terminals)
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        for parent in inputs.get(node_id, []):
            if parent not in seen:
                stack.append(parent)
    return list(seen)


def validate_for_run(graph: ParsedGraph) -> None:
    """运行前校验：每个终点都接好，文件存在，节点参数完整。"""
    if not graph.terminals:
        raise FriendlyError(
            "还没有输出节点",
            detail="流水线需要至少一个「输出节点」或「拆分节点」作为终点。",
            hint="从左侧节点库拖入输出节点，并把最后一步连到它。",
        )

    for node_id in graph.terminals:
        node = graph.nodes[node_id]
        if not graph.inputs[node_id]:
            raise FriendlyError(
                f"{node.label}还没有输入",
                detail="终点需要接收上一步的数据。",
                hint="请把文件 / 合并 / 清洗节点连到它。",
            )

    for node in graph.nodes.values():
        if node.id not in graph.reachable:
            continue
        if node.type == NODE_FILE:
            path = normalize_path(node.data.get("path", ""))
            if not path:
                # 模板里的空占位节点可以保留：只要它只流向合并节点，
                # 合并时会跳过；如果直接流向清洗 / 拆分 / 输出，则必须选文件。
                targets = graph.outputs.get(node.id, [])
                if targets and all(graph.nodes[target].type == NODE_MERGE
                                   for target in targets):
                    continue
                raise FriendlyError(
                    f"{node.label}还没有选择文件",
                    detail="可以点击节点卡片上的「选择文件」，或直接把 Excel 拖到卡片上。",
                )
            _validate_file_node(node)
        elif node.type == NODE_MERGE:
            if not graph.inputs[node.id]:
                raise FriendlyError(
                    "合并节点还没有输入文件",
                    hint="请把至少一个 Excel 文件节点连到合并节点。",
                )
            if not any(graph.nodes[parent].type == NODE_FILE
                       for parent in graph.inputs[node.id]):
                raise FriendlyError("合并节点缺少文件输入")
            if not any(normalize_path(graph.nodes[parent].data.get("path", ""))
                       for parent in graph.inputs[node.id]):
                raise FriendlyError(
                    "合并节点还没有可用的文件",
                    detail="连接到合并节点的文件卡片都是空的。",
                    hint="请把 Excel 文件拖到左侧文件节点上。",
                )
        elif node.type == NODE_CLEAN:
            if len(graph.inputs[node.id]) != 1:
                raise FriendlyError("清洗节点需要且只能有一个输入")
        elif node.type == NODE_SPLIT:
            if len(graph.inputs[node.id]) != 1:
                raise FriendlyError("拆分节点需要且只能有一个输入")
            column = _as_text(node.data.get("column"))
            if not column:
                raise FriendlyError(
                    "拆分节点还没有填写拆分列",
                    detail="请双击拆分节点，选择按哪一列分组。",
                )
            mode = _as_text(node.data.get("mode"), "file")
            if mode not in {"file", "sheet"}:
                raise FriendlyError("拆分方式不正确")
            template = _as_text(node.data.get("filenameTemplate"), DEFAULT_SPLIT_TEMPLATE)
            if mode == "file":
                try:
                    validate_filename_template(template)
                except Exception as exc:  # noqa: BLE001
                    raise FriendlyError(
                        "拆分文件名模板不正确",
                        detail=str(exc),
                        hint="模板需要包含 {分组列值}，例如 {分组列值}.xlsx。",
                    ) from exc
        elif node.type == NODE_OUTPUT:
            if len(graph.inputs[node.id]) != 1:
                raise FriendlyError("输出节点需要且只能有一个输入")

    for terminal_id in graph.terminals:
        if not _node_has_data(terminal_id, graph):
            raise FriendlyError(
                "流程里还没有可处理的数据",
                detail="终点上游的文件节点都还没有选择 Excel 文件。",
                hint="请把 Excel 文件拖到文件节点，或先载入一键合并模板。",
            )

    data_nodes = [node for node in graph.nodes.values()
                  if node.id in graph.reachable and node.type in DATA_NODE_TYPES]
    if not data_nodes:
        raise FriendlyError(
            "流程里还没有可处理的数据",
            hint="请把 Excel 文件拖到文件节点，或先载入一键合并模板。",
        )


def _node_has_data(node_id: str, graph: ParsedGraph,
                   seen: Optional[set] = None) -> bool:
    """判断节点上游是否存在至少一个真正选了文件的文件节点。"""
    seen = seen or set()
    if node_id in seen:
        return False
    seen.add(node_id)
    node = graph.nodes[node_id]
    if node.type == NODE_FILE:
        return bool(normalize_path(node.data.get("path", "")))
    if node.type == NODE_MERGE:
        return any(_node_has_data(parent, graph, seen)
                   for parent in graph.inputs.get(node_id, []))
    if node.type == NODE_CLEAN:
        return any(_node_has_data(parent, graph, seen)
                   for parent in graph.inputs.get(node_id, []))
    if node.type in TERMINAL_NODE_TYPES:
        return any(_node_has_data(parent, graph, seen)
                   for parent in graph.inputs.get(node_id, []))
    return False


def _validate_file_node(node: PipelineNode) -> None:
    path = normalize_path(node.data.get("path", ""))
    if not path:
        raise FriendlyError(
            f"{node.label}还没有选择文件",
            detail="可以点击节点卡片上的「选择文件」，或直接把 Excel 拖到卡片上。",
        )
    if not os.path.exists(path):
        raise FriendlyError(
            "找不到文件",
            detail=f"「{os.path.basename(path)}」可能已被移动、重命名或删除。",
            hint="请重新把文件拖入该节点。",
        )
    extension = os.path.splitext(path)[1].lower()
    if extension not in EXCEL_EXTENSIONS:
        raise FriendlyError(
            "不支持的文件类型",
            detail=f"「{os.path.basename(path)}」不是 Excel 文件。",
            hint="流水线目前支持 .xlsx / .xls / .xlsm。",
        )


# --------------------------------------------------------------------------- #
# 运行
# --------------------------------------------------------------------------- #
def run_pipeline(graph: Mapping[str, Any],
                 *,
                 default_output_dir: str,
                 emit: Optional[Callable[[str, Dict[str, Any]], None]] = None,
                 log: Optional[Callable[[str, str], None]] = None,
                 progress: Optional[Callable[[int, int], None]] = None,
                 is_cancelled: Optional[Callable[[], bool]] = None) -> Dict[str, Any]:
    """执行整张流程图，返回输出路径与统计。

    回调约定：
      - ``emit(name, payload)``：前端结构化事件（node-start / node-done ...）
      - ``log(message, level)``：人类可读日志
      - ``progress(done, total)``：整体节点进度
      - ``is_cancelled()``：在安全点检查用户是否点击停止
    """
    emit = emit or (lambda _name, _payload: None)
    log = log or (lambda _message, _level="info": None)
    progress = progress or (lambda _done, _total: None)
    is_cancelled = is_cancelled or (lambda: False)

    parsed = parse_graph(graph)
    validate_for_run(parsed)

    plan = [node_id for node_id in parsed.order
            if node_id in parsed.reachable]
    total = max(len(plan), 1)
    started = time.perf_counter()

    if parsed.ignored:
        log(f"ℹ 有 {len(parsed.ignored)} 个未连接到终点的节点，本次不会执行", "warn")

    os.makedirs(default_output_dir, exist_ok=True)
    temp_root = os.path.join(default_output_dir, ".pipeline_tmp")
    os.makedirs(temp_root, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="run_", dir=temp_root)

    context = RunContext(
        graph=parsed,
        default_output_dir=default_output_dir,
        temp_dir=temp_dir,
        emit=emit,
        log=log,
        progress=progress,
        is_cancelled=is_cancelled,
    )

    emit("run-start", {
        "total": total,
        "nodeIds": plan,
        "ignored": len(parsed.ignored),
    })
    log(f"▶ 开始运行流水线：{len(plan)} 个节点", "info")

    try:
        for index, node_id in enumerate(plan, start=1):
            context.check_cancelled()
            node = parsed.nodes[node_id]
            emit("node-start", {"nodeId": node_id, "index": index, "total": total})
            node_started = time.perf_counter()
            try:
                stats = _execute_node(node, context)
            except PipelineCancelled:
                raise
            except Exception as exc:  # noqa: BLE001
                record_exception(exc, f"流水线节点 {node.label}")
                info = explain(exc)
                emit("node-error", {
                    "nodeId": node_id,
                    "message": info.title,
                    "detail": info.detail,
                    "hint": info.hint,
                })
                raise PipelineNodeError(node_id, node.label, exc) from exc

            elapsed_ms = int((time.perf_counter() - node_started) * 1000)
            payload = dict(stats or {})
            payload.update({"nodeId": node_id, "ms": elapsed_ms})
            context.results[node_id] = payload
            emit("node-done", payload)
            progress(index, total)
            context.check_cancelled()

        elapsed = time.perf_counter() - started
        summary = _build_summary(context, elapsed)
        result = {
            "ok": True,
            "elapsed": round(elapsed, 2),
            "summary": summary,
            "outputs": list(context.output_paths),
            "nodes": dict(context.results),
        }
        log(f"✔ 流水线运行完成，用时 {elapsed:.1f} 秒", "success")
        return result
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _execute_node(node: PipelineNode, context: RunContext) -> Dict[str, Any]:
    if node.type == NODE_FILE:
        return _execute_file(node, context)
    if node.type == NODE_MERGE:
        return _execute_merge(node, context)
    if node.type == NODE_CLEAN:
        return _execute_clean(node, context)
    if node.type == NODE_SPLIT:
        return _execute_split(node, context)
    if node.type == NODE_OUTPUT:
        return _execute_output(node, context)
    raise FriendlyError("不支持的节点类型", detail=node.type)


def _execute_file(node: PipelineNode, context: RunContext) -> Dict[str, Any]:
    path = normalize_path(node.data.get("path", ""))
    name = os.path.basename(path)
    # 如果文件只流向合并节点，合并函数会自己读取，这里无需重复读一遍。
    needs_frames = any(
        context.graph.nodes[target].type != NODE_MERGE
        for target in context.graph.outputs.get(node.id, []))
    if not path:
        if needs_frames:
            raise FriendlyError(
                f"{node.label}还没有选择文件",
                hint="请点击文件卡片选择 Excel，或直接把文件拖到卡片上。",
            )
        context.log("ℹ 跳过空文件节点（未选择文件）", "info")
        return {
            "rows": None, "cols": 0, "sheets": 0, "files": 0,
            "name": "", "skipped": True, "preview": _graph_preview(node),
        }
    if not needs_frames:
        columns = node.data.get("columns") or []
        sheets = node.data.get("sheets") or []
        context.log(f"✓ {name}：已交给合并节点", "info")
        return {
            "rows": None, "cols": len(columns), "sheets": len(sheets),
            "files": 1, "name": name,
            "preview": _graph_preview(node),
        }

    workbook = read_workbook(path)
    context.frames[node.id] = workbook
    rows = sum(len(frame) for frame in workbook.values())
    cols = max((len(frame.columns) for frame in workbook.values()), default=0)
    context.log(f"✓ {name}：读取 {len(workbook)} 个工作表，{rows} 行", "success")
    return {
        "rows": rows, "cols": cols, "sheets": len(workbook), "files": 1,
        "name": name,
        "preview": _frames_preview(workbook),
    }


def _execute_merge(node: PipelineNode, context: RunContext) -> Dict[str, Any]:
    sources = [context.graph.nodes[parent] for parent in context.graph.inputs[node.id]]
    sources.sort(key=lambda item: (item.position[1], item.position[0]))
    files: List[str] = []
    skipped = 0
    for source in sources:
        path = normalize_path(source.data.get("path", ""))
        if not path:
            skipped += 1
            continue
        if path not in files:
            files.append(path)
    if not files:
        raise FriendlyError("合并节点没有可用的文件", hint="请把 Excel 文件节点连到合并节点。")
    if skipped:
        context.log(f"ℹ 已跳过 {skipped} 个空文件节点（未选择文件）", "info")

    data = node.data
    add_source = _as_bool(data.get("addSource"), True)
    all_sheets = _as_bool(data.get("allSheets"), True)
    source_column = _as_text(data.get("sourceColumn"), "来源文件")
    sheet_column = _as_text(data.get("sheetColumn"), "来源工作表")
    alignment = _as_text(data.get("alignment"), ALIGNMENT_UNION)
    if alignment not in {ALIGNMENT_UNION, ALIGNMENT_INTERSECTION}:
        alignment = ALIGNMENT_UNION
    ignore_empty = _as_bool(data.get("ignoreEmpty"), True)
    sort_columns = _as_text(data.get("sortColumns"))
    sort_ascending = _as_bool(data.get("sortAscending"), True)

    if add_source and all_sheets and source_column == sheet_column:
        raise FriendlyError(
            "来源文件列与来源工作表列不能同名",
            detail=f"两个来源列都叫「{source_column}」。",
            hint="请双击合并节点修改来源列名称，或关闭「添加来源列」。",
        )

    safe_id = sanitize_filename(node.id) or "node"
    output_path = os.path.join(context.temp_dir, f"merge_{safe_id}.xlsx")

    def node_progress(done: int, total: int) -> None:
        context.check_cancelled()
        context.emit("node-progress", {
            "nodeId": node.id, "done": int(done), "total": int(total),
            "unit": "files",
        })

    context.log(f"合并 {len(files)} 个文件……", "info")
    result = merge_files(
        files,
        output_path,
        all_sheets=all_sheets,
        add_source=add_source,
        source_column=source_column,
        sheet_column=sheet_column,
        alignment=alignment,
        ignore_empty_sheets=ignore_empty,
        sort_columns=sort_columns,
        sort_ascending=sort_ascending,
        progress=node_progress,
        log=context.log,
    )
    frames = read_workbook(output_path)
    context.frames[node.id] = frames
    first = next(iter(frames.values())) if frames else pd.DataFrame()
    return {
        "rows": int(result.get("rows", len(first))),
        "cols": int(result.get("cols", len(first.columns))),
        "files": len(files),
        "failed": int(result.get("failed", 0)),
        "sheets": len(frames),
        "preview": _frames_preview(frames),
    }


def _clean_rule_keys(data: Mapping[str, Any]) -> List[str]:
    mapping = (
        ("removeEmptyRows", "remove_empty_rows"),
        ("removeEmptyCols", "remove_empty_cols"),
        ("stripText", "strip_text"),
        ("normalizeNumbers", "normalize_numbers"),
        ("normalizeDates", "normalize_dates"),
        ("dropDuplicates", "drop_duplicates"),
    )
    selected = [key for field_name, key in mapping
                if _as_bool(data.get(field_name), False)]
    return normalize_global_rules(selected)


def _collect_source_columns(node_id: str, graph: ParsedGraph,
                           seen: Optional[set] = None) -> set:
    """找出上游合并节点插入的来源列（清洗空行时应忽略它们）。"""
    seen = seen or set()
    if node_id in seen:
        return set()
    seen.add(node_id)
    result: set = set()
    for parent in graph.inputs.get(node_id, []):
        parent_node = graph.nodes[parent]
        if parent_node.type == NODE_MERGE and _as_bool(
                parent_node.data.get("addSource"), True):
            result.add(_as_text(parent_node.data.get("sourceColumn"), "来源文件"))
            if _as_bool(parent_node.data.get("allSheets"), True):
                result.add(_as_text(parent_node.data.get("sheetColumn"), "来源工作表"))
        elif parent_node.type == NODE_CLEAN:
            result |= _collect_source_columns(parent, graph, seen)
    return result


def _execute_clean(node: PipelineNode, context: RunContext) -> Dict[str, Any]:
    parent = context.graph.inputs[node.id][0]
    if parent not in context.frames:
        raise FriendlyError("清洗节点没有收到数据")
    source_frames = context.frames[parent]

    keys = _clean_rule_keys(node.data)
    if not keys:
        context.log("ℹ 清洗节点未启用任何规则，数据将原样传向下一个节点", "info")
    date_format = _as_text(node.data.get("dateFormat"), "%Y-%m-%d") or "%Y-%m-%d"
    if "normalize_dates" in keys and not valid_date_format(date_format):
        context.log(f"⚠ 日期格式无效：{date_format}，已改用 %Y-%m-%d", "warn")
        date_format = "%Y-%m-%d"

    # 合并节点会插入「来源文件 / 来源工作表」列，这些列永远有值。
    # 判断空行时必须排除它们，否则合并后的空白数据行永远删不掉。
    source_columns = (
        _collect_source_columns(node.id, context.graph)
        if "remove_empty_rows" in keys else set())

    stats: Dict[str, Any] = {}
    out_frames: Dict[str, pd.DataFrame] = {}
    in_rows = sum(len(frame) for frame in source_frames.values())
    for sheet_name, frame in source_frames.items():
        before = len(frame)
        cleaned = frame.copy()
        cleaned.columns = [str(column).strip() for column in cleaned.columns]
        if source_columns:
            data_columns = [column for column in cleaned.columns
                            if column not in source_columns]
            if data_columns:
                blank = cleaned[data_columns].isna()
                for column in data_columns:
                    series = cleaned[column]
                    if (pd.api.types.is_object_dtype(series)
                            or pd.api.types.is_string_dtype(series)):
                        blank[column] = blank[column] | series.map(
                            lambda value: isinstance(value, str)
                            and not value.strip())
                drop_mask = blank.all(axis=1)
                removed = int(drop_mask.sum())
                if removed:
                    cleaned = cleaned.loc[~drop_mask].reset_index(drop=True)
                    context.log(
                        f"ℹ [{sheet_name}] 忽略来源列后删除 {removed} 个空行",
                        "info")
        cleaned = apply_global_rules(
            cleaned, keys,
            date_format=date_format,
            file_name=os.path.basename(context.graph.nodes[parent].data.get("path", "")),
            sheet_name=str(sheet_name),
            log=context.log,
            stats=stats,
        )
        cleaned = apply_column_bindings(
            cleaned, [],
            date_format=date_format,
            file_name="",
            sheet_name=str(sheet_name),
            log=context.log,
            stats=stats,
        )
        cleaned = cleaned.reset_index(drop=True)
        stats["removed_rows"] = (
            stats.get("removed_rows", 0) + max(before - len(cleaned), 0))
        out_frames[str(sheet_name)] = cleaned

    context.frames[node.id] = out_frames
    out_rows = sum(len(frame) for frame in out_frames.values())
    cols = max((len(frame.columns) for frame in out_frames.values()), default=0)
    removed = max(in_rows - out_rows, 0)
    parts = [f"{in_rows} → {out_rows} 行"]
    if removed:
        parts.append(f"减少 {removed} 行")
    if stats.get("removed_dups"):
        parts.append(f"去重 {stats['removed_dups']} 行")
    if stats.get("numbers"):
        parts.append(f"数字统一 {stats['numbers']} 个")
    if stats.get("date_cols"):
        parts.append(f"日期列 {stats['date_cols']} 个")
    context.log("✓ 清洗完成：" + "，".join(parts), "success")
    return {
        "rows": out_rows, "cols": cols, "sheets": len(out_frames),
        "inRows": in_rows, "outRows": out_rows, "removedRows": removed,
        "removedDups": int(stats.get("removed_dups", 0)),
        "preview": _frames_preview(out_frames),
    }


def _execute_split(node: PipelineNode, context: RunContext) -> Dict[str, Any]:
    parent = context.graph.inputs[node.id][0]
    if parent not in context.frames:
        raise FriendlyError("拆分节点没有收到数据")
    source_frames = context.frames[parent]
    column = _as_text(node.data.get("column"))
    if not column:
        raise FriendlyError("拆分节点还没有填写拆分列")
    mode = _as_text(node.data.get("mode"), "file")
    if mode not in {"file", "sheet"}:
        mode = "file"
    template = _as_text(node.data.get("filenameTemplate"), DEFAULT_SPLIT_TEMPLATE)
    if mode == "file":
        try:
            template = validate_filename_template(template)
        except Exception as exc:  # noqa: BLE001
            raise FriendlyError(
                "拆分文件名模板不正确", detail=str(exc),
                hint="模板需要包含 {分组列值}，例如 {分组列值}.xlsx。",
            ) from exc
    skip_empty = _as_bool(node.data.get("skipEmpty"), True)

    output_dir = _resolve_directory(
        node.data.get("outputDir"),
        context.default_output_dir,
        f"拆分结果_{_stamp()}",
    )
    os.makedirs(output_dir, exist_ok=True)

    safe_id = sanitize_filename(node.id) or "node"
    input_path = os.path.join(context.temp_dir, f"split_input_{safe_id}.xlsx")
    write_workbook(source_frames, input_path)

    def node_progress(done: int, total: int) -> None:
        context.check_cancelled()
        context.emit("node-progress", {
            "nodeId": node.id, "done": int(done), "total": int(total),
            "unit": "files",
        })

    result = split_by_column(
        [input_path],
        column,
        output_dir,
        mode=mode,
        all_sheets=True,
        skip_empty_groups=skip_empty,
        filename_template=template,
        progress=node_progress,
        log=context.log,
    )
    in_rows = sum(len(frame) for frame in source_frames.values())
    context.output_paths.append({
        "path": output_dir, "kind": "folder",
        "label": f"拆分结果（{result.get('files', 0)} 个文件）",
    })
    return {
        "rows": in_rows,
        "cols": max((len(frame.columns) for frame in source_frames.values()), default=0),
        "sheets": len(source_frames),
        "files": int(result.get("files", 0)),
        "groups": int(result.get("groups", 0)),
        "skipped": int(result.get("skipped", 0)),
        "output": output_dir,
    }


def _execute_output(node: PipelineNode, context: RunContext) -> Dict[str, Any]:
    parent = context.graph.inputs[node.id][0]
    if parent not in context.frames:
        raise FriendlyError("输出节点没有收到数据")
    frames = context.frames[parent]
    if not frames:
        raise FriendlyError("输出节点没有可写出的数据")

    output_dir = _resolve_directory(
        node.data.get("outputDir"), context.default_output_dir, "")
    os.makedirs(output_dir, exist_ok=True)
    file_name = _render_output_name(
        _as_text(node.data.get("fileName"), DEFAULT_OUTPUT_NAME))
    output_path = os.path.join(output_dir, file_name)
    auto_rename = _as_bool(node.data.get("autoRename"), True)
    if auto_rename:
        output_path = unique_path(output_path)

    if len(frames) == 1:
        sheet_name, frame = next(iter(frames.items()))
        write_dataframe(frame, output_path, sheet_name=sheet_name or "Sheet1")
    else:
        write_workbook(frames, output_path)

    rows = sum(len(frame) for frame in frames.values())
    cols = max((len(frame.columns) for frame in frames.values()), default=0)
    context.log(f"✓ 已写出：{output_path}", "success")
    context.output_paths.append({
        "path": output_path, "kind": "file",
        "label": os.path.basename(output_path),
    })
    return {
        "rows": rows, "cols": cols, "sheets": len(frames),
        "files": 1, "output": output_path,
        "name": os.path.basename(output_path),
        "preview": _frames_preview(frames),
    }


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #
def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _resolve_directory(raw_value: Any, default_root: str, label: str) -> str:
    text = normalize_path(raw_value) if raw_value else ""
    if text:
        if not os.path.isabs(text):
            text = os.path.join(default_root, text)
        return os.path.normpath(text)
    return os.path.join(default_root, label) if label else default_root


def _render_output_name(template: str) -> str:
    now = datetime.now()
    values = {
        "{日期}": now.strftime("%Y-%m-%d"),
        "{时间}": now.strftime("%H%M%S"),
        "{时间戳}": now.strftime("%Y%m%d_%H%M%S"),
        "{年月}": now.strftime("%Y%m"),
    }
    text = str(template or DEFAULT_OUTPUT_NAME)
    for key, value in values.items():
        text = text.replace(key, value)
    text = sanitize_filename(text)
    if not text.lower().endswith(".xlsx"):
        text += ".xlsx"
    return text


def _cell_text(value: Any) -> str:
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


def _frame_payload(frame: pd.DataFrame, limit: int = 5,
                   max_cols: int = 10) -> Dict[str, Any]:
    preview = preview_frame(frame, rows=limit)
    columns = list(preview.columns[:max_cols])
    rows = [[cell for cell in row[:max_cols]] for row in preview.rows]
    return {
        "columns": columns,
        "rows": rows,
        "totalCols": len(preview.columns),
        "totalRows": len(frame),
    }


def _frames_preview(frames: Mapping[str, pd.DataFrame]) -> Dict[str, Any]:
    if not frames:
        return {"columns": [], "rows": [], "totalCols": 0, "totalRows": 0}
    first_key = next(iter(frames))
    payload = _frame_payload(frames[first_key])
    payload["sheet"] = str(first_key)
    return payload


def _graph_preview(node: PipelineNode) -> Dict[str, Any]:
    columns = node.data.get("columns") or []
    rows = node.data.get("rows") or []
    if not isinstance(columns, list):
        columns = []
    if not isinstance(rows, list):
        rows = []
    return {
        "columns": [str(item) for item in columns[:10]],
        "rows": [[_cell_text(cell) for cell in row[:10]]
                 for row in rows[:5] if isinstance(row, list)],
        "totalCols": len(columns),
        "totalRows": node.data.get("totalRows") or 0,
    }


def _build_summary(context: RunContext, elapsed: float) -> str:
    outputs = context.output_paths
    if not outputs:
        return f"运行完成，用时 {elapsed:.1f} 秒，但没有生成输出文件。"
    parts = [item.get("label", "") for item in outputs if item.get("label")]
    return f"运行完成：{'、'.join(parts)}（用时 {elapsed:.1f} 秒）"


# --------------------------------------------------------------------------- #
# 模板用的图清洗
# --------------------------------------------------------------------------- #
def strip_graph_for_template(graph: Mapping[str, Any]) -> Dict[str, Any]:
    """把画布图变成可复用模板：去掉本地文件路径、预览数据与输出目录。"""
    parsed = parse_graph(graph)
    nodes: List[Dict[str, Any]] = []
    node_order = [node_id for node_id in parsed.order]
    for node_id in node_order:
        node = parsed.nodes[node_id]
        data = dict(node.data)
        if node.type == NODE_FILE:
            data = {
                "path": "", "name": "", "columns": [], "rows": [],
                "sheets": [], "loading": False, "error": "",
            }
        elif node.type == NODE_OUTPUT:
            data = {
                "fileName": _as_text(data.get("fileName"), DEFAULT_OUTPUT_NAME),
                "outputDir": "",
                "autoRename": _as_bool(data.get("autoRename"), True),
            }
        elif node.type == NODE_SPLIT:
            data = {
                "column": _as_text(data.get("column")),
                "mode": _as_text(data.get("mode"), "file"),
                "filenameTemplate": _as_text(
                    data.get("filenameTemplate"), DEFAULT_SPLIT_TEMPLATE),
                "skipEmpty": _as_bool(data.get("skipEmpty"), True),
                "outputDir": "",
            }
        elif node.type == NODE_MERGE:
            data = {
                "addSource": _as_bool(data.get("addSource"), True),
                "sourceColumn": _as_text(data.get("sourceColumn"), "来源文件"),
                "sheetColumn": _as_text(data.get("sheetColumn"), "来源工作表"),
                "allSheets": _as_bool(data.get("allSheets"), True),
                "alignment": _as_text(data.get("alignment"), ALIGNMENT_UNION),
                "ignoreEmpty": _as_bool(data.get("ignoreEmpty"), True),
                "sortColumns": _as_text(data.get("sortColumns")),
                "sortAscending": _as_bool(data.get("sortAscending"), True),
            }
        elif node.type == NODE_CLEAN:
            data = {
                "removeEmptyRows": _as_bool(data.get("removeEmptyRows"), True),
                "removeEmptyCols": _as_bool(data.get("removeEmptyCols"), True),
                "stripText": _as_bool(data.get("stripText"), True),
                "normalizeNumbers": _as_bool(data.get("normalizeNumbers"), True),
                "normalizeDates": _as_bool(data.get("normalizeDates"), True),
                "dropDuplicates": _as_bool(data.get("dropDuplicates"), False),
                "dateFormat": _as_text(data.get("dateFormat"), "%Y-%m-%d"),
            }
        nodes.append({
            "id": node.id,
            "type": node.type,
            "position": {"x": node.position[0], "y": node.position[1]},
            "data": data,
        })
    edges = [{"id": f"e-{source}-{target}", "source": source, "target": target}
             for source, target in parsed.edges]
    return {"version": 1, "nodes": nodes, "edges": edges}
