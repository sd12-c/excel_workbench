export const NODE_FILE = 'file'
export const NODE_MERGE = 'merge'
export const NODE_CLEAN = 'clean'
export const NODE_SPLIT = 'split'
export const NODE_OUTPUT = 'output'

export const NODE_TYPES = [NODE_FILE, NODE_MERGE, NODE_CLEAN, NODE_SPLIT, NODE_OUTPUT]

export const NODE_META = {
  [NODE_FILE]: {
    label: '文件节点',
    short: '文件',
    tone: 'file',
    description: 'Excel 起点 · 表头预览',
    tip: '拖入 Excel 文件，或双击节点更换文件',
  },
  [NODE_MERGE]: {
    label: '合并节点',
    short: '合并',
    tone: 'merge',
    description: '多个文件合成一张表',
    tip: '把多个文件节点连到合并节点',
  },
  [NODE_CLEAN]: {
    label: '清洗节点',
    short: '清洗',
    tone: 'clean',
    description: '去空行 · 统一格式',
    tip: '接收一张表，清洗后继续向下传',
  },
  [NODE_SPLIT]: {
    label: '拆分节点',
    short: '拆分',
    tone: 'split',
    description: '按列分组拆成多个',
    tip: '管线终点：直接输出多个 Excel',
  },
  [NODE_OUTPUT]: {
    label: '输出节点',
    short: '输出',
    tone: 'output',
    description: '保存最终 xlsx',
    tip: '管线终点：保存最终结果',
  },
}

export const NODE_WIDTH = {
  [NODE_FILE]: 286,
  [NODE_MERGE]: 238,
  [NODE_CLEAN]: 238,
  [NODE_SPLIT]: 252,
  [NODE_OUTPUT]: 252,
}

let seq = 0

export function uid(prefix = 'n') {
  seq += 1
  return `${prefix}-${Date.now().toString(36)}-${seq.toString(36)}`
}

export function basename(path) {
  const text = String(path || '')
  const parts = text.split(/[\\/]/)
  return parts[parts.length - 1] || text
}

export function normalizePath(path) {
  return String(path || '').replace(/\//g, '\\').toLowerCase()
}

export function samePath(a, b) {
  return normalizePath(a) === normalizePath(b) && Boolean(a)
}

export function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return String(value)
  return number.toLocaleString('zh-CN')
}

export function formatDuration(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value) || value < 0) return ''
  if (value < 1000) return `${Math.round(value)} ms`
  return `${(value / 1000).toFixed(1)} s`
}

export function defaultData(type) {
  switch (type) {
    case NODE_FILE:
      return {
        path: '', name: '', columns: [], rows: [], sheets: [],
        loading: false, error: '', runtime: null,
      }
    case NODE_MERGE:
      return {
        addSource: true, sourceColumn: '来源文件',
        sheetColumn: '来源工作表', allSheets: true,
        alignment: 'union', ignoreEmpty: true,
        sortColumns: '', sortAscending: true, runtime: null,
      }
    case NODE_CLEAN:
      return {
        removeEmptyRows: true, removeEmptyCols: true,
        stripText: true, normalizeNumbers: true,
        normalizeDates: true, dropDuplicates: false,
        dateFormat: '%Y-%m-%d', runtime: null,
      }
    case NODE_SPLIT:
      return {
        column: '', mode: 'file',
        filenameTemplate: '{分组列值}.xlsx',
        skipEmpty: true, outputDir: '', runtime: null,
      }
    case NODE_OUTPUT:
      return {
        fileName: '流水线结果_{日期}.xlsx',
        outputDir: '', autoRename: true, runtime: null,
      }
    default:
      return { runtime: null }
  }
}

export function makeNode(type, position, data = {}) {
  return {
    id: uid(type),
    type,
    position: { x: Math.round(position?.x || 0), y: Math.round(position?.y || 0) },
    style: { width: NODE_WIDTH[type] || 240 },
    data: { ...defaultData(type), ...data, runtime: null },
  }
}

export function makeEdge(source, target) {
  return {
    id: uid('e'),
    source,
    target,
    type: 'smoothstep',
    animated: false,
  }
}

export function nodeLabel(node) {
  return NODE_META[node?.type]?.label || '节点'
}

export function collectFileNodes(nodes) {
  return nodes.filter((node) => node.type === NODE_FILE)
}

export function inputCounts(edges) {
  const counts = new Map()
  edges.forEach((edge) => {
    counts.set(edge.target, (counts.get(edge.target) || 0) + 1)
  })
  return counts
}

export function outputsOf(edges, nodeId) {
  return edges.filter((edge) => edge.source === nodeId).map((edge) => edge.target)
}

export function inputsOf(edges, nodeId) {
  return edges.filter((edge) => edge.target === nodeId).map((edge) => edge.source)
}

export function upstreamColumns(nodes, edges, nodeId) {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const seen = new Set()
  const columns = []
  const add = (items) => {
    (items || []).forEach((item) => {
      const text = String(item || '').trim()
      if (text && !columns.includes(text)) columns.push(text)
    })
  }
  const walk = (id) => {
    if (seen.has(id)) return
    seen.add(id)
    const node = byId.get(id)
    if (!node) return
    if (node.type === NODE_FILE) {
      add(node.data.columns)
    } else if (node.data?.runtime?.preview?.columns) {
      add(node.data.runtime.preview.columns)
    }
    if (node.type === NODE_MERGE && node.data?.addSource) {
      add([node.data.sourceColumn, node.data.sheetColumn])
    }
    inputsOf(edges, id).forEach(walk)
  }
  walk(nodeId)
  return columns
}

export function buildRunGraph(nodes, edges, name = '') {
  return {
    version: 1,
    name: String(name || ''),
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: {
        x: Number(node.position?.x || 0),
        y: Number(node.position?.y || 0),
      },
      data: runData(node),
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    })),
  }
}

function runData(node) {
  const data = node.data || {}
  switch (node.type) {
    case NODE_FILE:
      return { path: data.path || '' }
    case NODE_MERGE:
      return {
        addSource: Boolean(data.addSource),
        sourceColumn: String(data.sourceColumn || ''),
        sheetColumn: String(data.sheetColumn || ''),
        allSheets: Boolean(data.allSheets),
        alignment: data.alignment === 'intersection' ? 'intersection' : 'union',
        ignoreEmpty: Boolean(data.ignoreEmpty),
        sortColumns: String(data.sortColumns || ''),
        sortAscending: Boolean(data.sortAscending),
      }
    case NODE_CLEAN:
      return {
        removeEmptyRows: Boolean(data.removeEmptyRows),
        removeEmptyCols: Boolean(data.removeEmptyCols),
        stripText: Boolean(data.stripText),
        normalizeNumbers: Boolean(data.normalizeNumbers),
        normalizeDates: Boolean(data.normalizeDates),
        dropDuplicates: Boolean(data.dropDuplicates),
        dateFormat: String(data.dateFormat || '%Y-%m-%d'),
      }
    case NODE_SPLIT:
      return {
        column: String(data.column || ''),
        mode: data.mode === 'sheet' ? 'sheet' : 'file',
        filenameTemplate: String(data.filenameTemplate || ''),
        skipEmpty: Boolean(data.skipEmpty),
        outputDir: String(data.outputDir || ''),
      }
    case NODE_OUTPUT:
      return {
        fileName: String(data.fileName || ''),
        outputDir: String(data.outputDir || ''),
        autoRename: Boolean(data.autoRename),
      }
    default:
      return {}
  }
}

export function instantiateTemplate(template) {
  const graph = template?.graph || {}
  const rawNodes = Array.isArray(graph.nodes) ? graph.nodes : []
  const rawEdges = Array.isArray(graph.edges) ? graph.edges : []
  const ids = new Set()
  const nodes = rawNodes.map((raw) => {
    const type = NODE_META[raw.type] ? raw.type : NODE_FILE
    let id = String(raw.id || uid(type))
    while (ids.has(id)) id = uid(type)
    ids.add(id)
    const data = { ...defaultData(type), ...(raw.data || {}), runtime: null }
    if (type === NODE_FILE) {
      Object.assign(data, {
        path: '', name: '', columns: [], rows: [], sheets: [],
        loading: false, error: '',
      })
    }
    return {
      id,
      type,
      position: {
        x: Number(raw.position?.x || 0),
        y: Number(raw.position?.y || 0),
      },
      style: { width: NODE_WIDTH[type] || 240 },
      data,
      selected: false,
    }
  })
  const edges = rawEdges
    .filter((raw) => ids.has(String(raw.source)) && ids.has(String(raw.target)))
    .map((raw) => ({
      id: String(raw.id || uid('e')),
      source: String(raw.source),
      target: String(raw.target),
      type: 'smoothstep',
      animated: false,
    }))
  return { nodes, edges }
}

export function validateGraph(nodes, edges) {
  const byId = new Map(nodes.map((node) => [node.id, node]))
  if (!nodes.length) {
    return { ok: false, message: '画布上还没有节点，请先拖入 Excel 文件或载入模板。' }
  }
  if (!nodes.some((node) => node.type === NODE_FILE)) {
    return { ok: false, message: '至少需要一个文件节点作为起点。' }
  }
  const terminals = nodes.filter(
    (node) => node.type === NODE_OUTPUT || node.type === NODE_SPLIT)
  if (!terminals.length) {
    return { ok: false, message: '还没有终点：请从左侧拖入「输出节点」或「拆分节点」。' }
  }

  const incoming = new Map()
  const outgoing = new Map()
  nodes.forEach((node) => {
    incoming.set(node.id, [])
    outgoing.set(node.id, [])
  })

  for (const edge of edges) {
    const source = byId.get(edge.source)
    const target = byId.get(edge.target)
    if (!source || !target) {
      return { ok: false, message: '存在指向已删除节点的连线，请重新连接。' }
    }
    if (source.type === NODE_OUTPUT || source.type === NODE_SPLIT) {
      return { ok: false, message: `${nodeLabel(source)}是管线终点，不能再向下连接。` }
    }
    if (target.type === NODE_FILE) {
      return { ok: false, message: '文件节点是起点，不能作为连线终点。' }
    }
    if (target.type === NODE_MERGE && source.type !== NODE_FILE) {
      return {
        ok: false,
        message: '合并节点只能直接接收文件节点；合并后的数据请接清洗或输出。',
        nodeId: target.id,
      }
    }
    incoming.get(target.id).push(source.id)
    outgoing.get(source.id).push(target.id)
  }

  // 环检测
  const state = new Map()
  const visit = (id) => {
    const current = state.get(id) || 0
    if (current === 1) return false
    if (current === 2) return true
    state.set(id, 1)
    for (const next of outgoing.get(id) || []) {
      if (!visit(next)) return false
    }
    state.set(id, 2)
    return true
  }
  for (const node of nodes) {
    if (!visit(node.id)) {
      return { ok: false, message: '连线形成了环，数据只能单向流动。' }
    }
  }

  for (const node of nodes) {
    const count = incoming.get(node.id).length
    if (node.type === NODE_CLEAN && count !== 1) {
      return {
        ok: false,
        message: '清洗节点需要且只能有一条输入连线。',
        nodeId: node.id,
      }
    }
    if (node.type === NODE_SPLIT && count !== 1) {
      return {
        ok: false,
        message: '拆分节点需要且只能有一条输入连线。',
        nodeId: node.id,
      }
    }
    if (node.type === NODE_OUTPUT && count !== 1) {
      return {
        ok: false,
        message: '输出节点需要且只能有一条输入连线。',
        nodeId: node.id,
      }
    }
    if (node.type === NODE_MERGE) {
      const parents = incoming.get(node.id)
      if (!parents.length) {
        return {
          ok: false,
          message: '合并节点还没有输入文件。',
          nodeId: node.id,
        }
      }
      if (!parents.some((id) => Boolean(byId.get(id)?.data?.path))) {
        return {
          ok: false,
          message: '合并节点的文件卡片都还是空的，请先拖入 Excel。',
          nodeId: node.id,
        }
      }
    }
    if (node.type === NODE_FILE && !node.data.path) {
      const targets = outgoing.get(node.id) || []
      if (targets.some((id) => byId.get(id)?.type !== NODE_MERGE)) {
        return {
          ok: false,
          message: '文件节点还没有选择文件。',
          nodeId: node.id,
        }
      }
    }
    if (node.type === NODE_SPLIT && !String(node.data.column || '').trim()) {
      return {
        ok: false,
        message: '拆分节点还没有填写拆分列，请双击节点设置。',
        nodeId: node.id,
      }
    }
    if (node.type === NODE_OUTPUT && !String(node.data.fileName || '').trim()) {
      return {
        ok: false,
        message: '输出节点还没有填写文件名。',
        nodeId: node.id,
      }
    }
  }

  if (!terminals.every((node) => incoming.get(node.id).length === 1)) {
    return { ok: false, message: '终点节点还没有接上输入。' }
  }

  const hasData = (id, seen = new Set()) => {
    if (seen.has(id)) return false
    seen.add(id)
    const node = byId.get(id)
    if (!node) return false
    if (node.type === NODE_FILE) return Boolean(node.data.path)
    return (incoming.get(id) || []).some((parent) => hasData(parent, seen))
  }
  if (!terminals.some((node) => hasData(node.id))) {
    return { ok: false, message: '流程里还没有真正选择文件的文件节点。' }
  }

  return { ok: true, message: '' }
}

export function graphSummary(nodes, edges) {
  const counts = {}
  nodes.forEach((node) => {
    counts[node.type] = (counts[node.type] || 0) + 1
  })
  return { nodes: nodes.length, edges: edges.length, counts }
}

export function templateGraph(nodes, edges, name) {
  return buildRunGraph(nodes, edges, name)
}
