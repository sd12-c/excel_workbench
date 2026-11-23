import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Background, BackgroundVariant, Controls, MarkerType, ReactFlow,
  addEdge, useEdgesState, useNodesState, useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import './styles.css'

import { PipelineContext } from './context'
import { initBridge, call } from './bridge'
import { nodeTypes } from './nodes'
import {
  NODE_CLEAN, NODE_FILE, NODE_MERGE, NODE_META, NODE_OUTPUT, NODE_SPLIT,
  NODE_TYPES, NODE_WIDTH, basename, buildRunGraph, collectFileNodes,
  instantiateTemplate, makeEdge, makeNode, samePath, uid, validateGraph,
} from './graph'
import {
  AlertIcon, CheckIcon, CleanIcon, CloseIcon, FileIcon,
  FitIcon, FlowIcon, FolderIcon, GripIcon, HelpIcon, LogIcon, MergeIcon,
  OutputIcon, PlayIcon, PlusIcon, SaveIcon, SparkIcon, SplitIcon,
  StopIcon, TemplateIcon, TrashIcon, UploadIcon,
} from './icons'
import {
  ConfigModal, ConfirmModal, HelpModal, LogDrawer, SaveTemplateModal,
  TemplateDrawer, Toast,
} from './overlays'

const PALETTE_ICONS = {
  [NODE_FILE]: FileIcon,
  [NODE_MERGE]: MergeIcon,
  [NODE_CLEAN]: CleanIcon,
  [NODE_SPLIT]: SplitIcon,
  [NODE_OUTPUT]: OutputIcon,
}

function canReach(from, target, edges) {
  const stack = [from]
  const seen = new Set()
  while (stack.length) {
    const current = stack.pop()
    if (current === target) return true
    if (seen.has(current)) continue
    seen.add(current)
    edges.filter((edge) => edge.source === current).forEach((edge) => {
      if (!seen.has(edge.target)) stack.push(edge.target)
    })
  }
  return false
}

function timeNow() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

// 仅用于浏览器预览 / 文档截图：?demo=1 时展示一条已跑完的示例管线。
// 桌面端由 Python 桥提供真实数据，不会走到这里。
function demoGraph() {
  const fileData = (name, dept, amount) => ({
    path: `D:\\销售日报\\${name}`,
    name,
    columns: ['日期', '部门', '金额', '备注'],
    rows: [
      ['2026-11-18', dept, amount, '已完成'],
      ['2026-11-19', dept, '1,280.00', '已完成'],
      ['2026-11-20', dept, '960.50', '待复核'],
    ],
    sheets: ['明细'],
    loading: false,
    error: '',
    runtime: { status: 'done' },
  })
  const nodes = [
    {
      id: 'file-1', type: NODE_FILE, position: { x: 30, y: 30 },
      style: { width: NODE_WIDTH[NODE_FILE] }, data: fileData('销售一部.xlsx', '销售一部', '1,200.50'),
    },
    {
      id: 'file-2', type: NODE_FILE, position: { x: 30, y: 250 },
      style: { width: NODE_WIDTH[NODE_FILE] }, data: fileData('销售二部.xlsx', '销售二部', '2,000.00'),
    },
    {
      id: 'file-3', type: NODE_FILE, position: { x: 30, y: 470 },
      style: { width: NODE_WIDTH[NODE_FILE] }, data: fileData('销售三部.xlsx', '销售三部', '1,560.00'),
    },
    {
      id: 'merge-1', type: NODE_MERGE, position: { x: 350, y: 250 },
      style: { width: NODE_WIDTH[NODE_MERGE] },
      data: {
        addSource: true, sourceColumn: '来源文件', sheetColumn: '来源工作表',
        allSheets: true, alignment: 'union', ignoreEmpty: true,
        sortColumns: '', sortAscending: true,
        runtime: { status: 'done', rows: 9, cols: 6, files: 3, ms: 118 },
      },
    },
    {
      id: 'clean-1', type: NODE_CLEAN, position: { x: 640, y: 250 },
      style: { width: NODE_WIDTH[NODE_CLEAN] },
      data: {
        removeEmptyRows: true, removeEmptyCols: true, stripText: true,
        normalizeNumbers: true, normalizeDates: true, dropDuplicates: false,
        dateFormat: '%Y-%m-%d',
        runtime: { status: 'done', rows: 8, inRows: 9, outRows: 8, cols: 6, ms: 26 },
      },
    },
    {
      id: 'output-1', type: NODE_OUTPUT, position: { x: 930, y: 275 },
      style: { width: NODE_WIDTH[NODE_OUTPUT] },
      data: {
        fileName: '清洗结果_2026-11-23.xlsx',
        outputDir: 'E:\\python小项目\\excel_workbench_v1.3\\out_put',
        autoRename: true,
        runtime: {
          status: 'done', rows: 8, cols: 6, ms: 17,
          output: 'E:\\python小项目\\excel_workbench_v1.3\\out_put\\清洗结果_2026-11-23.xlsx',
        },
      },
    },
  ]
  const edges = [
    ['file-1', 'merge-1'], ['file-2', 'merge-1'], ['file-3', 'merge-1'],
    ['merge-1', 'clean-1'], ['clean-1', 'output-1'],
  ].map(([source, target]) => ({
    id: `e-${source}-${target}`, source, target, type: 'smoothstep', animated: false,
  }))
  return { nodes, edges }
}

export default function App() {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])
  const [templates, setTemplates] = useState([])
  const [activeTemplate, setActiveTemplate] = useState(null)
  const [outputDir, setOutputDir] = useState('')
  const [appVersion, setAppVersion] = useState('')
  const [bridgeReady, setBridgeReady] = useState(false)
  const [running, setRunning] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [runSummary, setRunSummary] = useState(null)
  const [logs, setLogs] = useState([])
  const [showLogs, setShowLogs] = useState(false)
  const [configNodeId, setConfigNodeId] = useState(null)
  const [showTemplates, setShowTemplates] = useState(false)
  const [showSave, setShowSave] = useState(false)
  const [showHelp, setShowHelp] = useState(false)
  const [confirmState, setConfirmState] = useState(null)
  const [toast, setToast] = useState(null)
  const [dragActive, setDragActive] = useState(false)
  const [banner, setBanner] = useState('')
  const [maxFiles, setMaxFiles] = useState(80)
  const [isMock, setIsMock] = useState(false)

  const { screenToFlowPosition, fitView } = useReactFlow()

  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  const runningRef = useRef(running)
  const templatesRef = useRef(templates)
  const progressRef = useRef(progress)
  const logsRef = useRef(logs)
  const runSummaryRef = useRef(runSummary)
  const initializedRef = useRef(false)
  const handlersRef = useRef(() => {})
  const addFilesRef = useRef(() => {})
  const pickFilesRef = useRef(() => {})
  const startRunRef = useRef(() => {})
  const applyTemplateRef = useRef(() => {})
  const toastTimer = useRef(null)
  const logSeq = useRef(0)
  const dirWaiters = useRef(new Map())
  const dirSeq = useRef(0)

  nodesRef.current = nodes
  edgesRef.current = edges
  runningRef.current = running
  templatesRef.current = templates
  progressRef.current = progress
  logsRef.current = logs
  runSummaryRef.current = runSummary

  const addLog = useCallback((message, level = 'info') => {
    const text = String(message || '').trim()
    if (!text) return
    const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
    if (!lines.length) return
    const time = timeNow()
    setLogs((prev) => [
      ...prev.slice(-249),
      ...lines.map((line) => ({ id: ++logSeq.current, time, message: line, level })),
    ])
  }, [])

  const showToast = useCallback((message, level = 'info') => {
    setToast({ id: `${Date.now()}-${Math.random()}`, message: String(message || ''), level })
    window.clearTimeout(toastTimer.current)
    toastTimer.current = window.setTimeout(() => setToast(null), 3800)
  }, [])

  useEffect(() => () => window.clearTimeout(toastTimer.current), [])

  const updateRuntime = useCallback((id, patch) => {
    setNodes((prev) => prev.map((node) => (
      node.id === id
        ? { ...node, data: { ...node.data, runtime: { ...(node.data.runtime || {}), ...patch } } }
        : node
    )))
  }, [setNodes])

  const deleteNode = useCallback((id) => {
    setNodes((prev) => prev.filter((node) => node.id !== id))
    setEdges((prev) => prev.filter((edge) => edge.source !== id && edge.target !== id))
    setConfigNodeId((current) => (current === id ? null : current))
    addLog('已删除一个节点', 'info')
  }, [setEdges, setNodes, addLog])

  const openConfig = useCallback((id) => {
    if (runningRef.current) {
      showToast('运行中不能修改节点参数，请等待或先停止', 'warn')
      return
    }
    setConfigNodeId(id)
  }, [showToast])

  const pickFiles = useCallback((nodeId = '') => {
    if (!call('pickFiles', String(nodeId || ''))) {
      showToast('桌面桥还没有就绪，无法打开文件选择器', 'error')
    }
  }, [showToast])

  const openPath = useCallback((path) => {
    if (!path) return
    if (!call('openPath', String(path))) {
      showToast('桌面桥还没有就绪', 'error')
    }
  }, [showToast])

  const applyTemplate = useCallback((template, options = {}) => {
    if (!template) return
    const built = instantiateTemplate(template)
    setNodes(built.nodes)
    setEdges(built.edges)
    setActiveTemplate({ id: template.id, name: template.name })
    setRunSummary(null)
    setConfigNodeId(null)
    setShowTemplates(false)
    setLogs([])
    setProgress({ done: 0, total: 0 })
    setBanner(`已载入「${template.name}」模板 · 把 Excel 拖到左侧文件卡片即可运行`)
    addLog(`已载入模板：${template.name}`, 'success')
    window.setTimeout(() => {
      try { fitView({ padding: 0.18, duration: 420 }) } catch (error) { /* ignore */ }
    }, 120)
    if (!options.silent) showToast(`已载入「${template.name}」`, 'success')
  }, [setNodes, setEdges, addLog, showToast, fitView])

  applyTemplateRef.current = applyTemplate

  const requestApplyTemplate = useCallback((template) => {
    if (!template) return
    if (runningRef.current) {
      showToast('运行中不能切换模板', 'warn')
      return
    }
    if (nodesRef.current.length) {
      setConfirmState({
        title: '载入模板',
        message: `载入「${template.name}」会替换当前画布，未保存的编排将丢失。`,
        confirmText: '载入模板',
        danger: true,
        onConfirm: () => applyTemplate(template),
      })
      return
    }
    applyTemplate(template)
  }, [applyTemplate, showToast])

  const clearCanvas = useCallback(() => {
    if (!nodesRef.current.length) return
    setConfirmState({
      title: '清空画布',
      message: '当前节点、连线和未保存的编排都会被清空。',
      confirmText: '清空画布',
      danger: true,
      onConfirm: () => {
        setNodes([])
        setEdges([])
        setActiveTemplate(null)
        setRunSummary(null)
        setConfigNodeId(null)
        setLogs([])
        setBanner('')
        setProgress({ done: 0, total: 0 })
        addLog('画布已清空', 'info')
      },
    })
  }, [setNodes, setEdges, addLog])

  const saveNodeConfig = useCallback((id, patch) => {
    setNodes((prev) => prev.map((node) => (
      node.id === id
        ? { ...node, data: { ...node.data, ...patch, runtime: null } }
        : node
    )))
    setRunSummary(null)
    setProgress({ done: 0, total: 0 })
    addLog('节点参数已更新，请重新运行', 'info')
  }, [setNodes, addLog])

  /* ------------------------------------------------------------ 画布交互 */
  const onConnect = useCallback((connection) => {
    const { source, target } = connection
    if (!source || !target) return
    const byId = new Map(nodesRef.current.map((node) => [node.id, node]))
    const sourceNode = byId.get(source)
    const targetNode = byId.get(target)
    if (!sourceNode || !targetNode) return
    if (source === target) {
      showToast('节点不能连到自己', 'warn')
      return
    }
    if (sourceNode.type === NODE_OUTPUT || sourceNode.type === NODE_SPLIT) {
      showToast('输出 / 拆分节点是管线终点，不能再向下连接', 'warn')
      return
    }
    if (targetNode.type === NODE_FILE) {
      showToast('文件节点是起点，不能接收连线', 'warn')
      return
    }
    if (targetNode.type === NODE_MERGE && sourceNode.type !== NODE_FILE) {
      showToast('合并节点只能直接接收文件节点', 'warn')
      return
    }
    if (edgesRef.current.some((edge) => edge.source === source && edge.target === target)) {
      showToast('这两个节点已经连过了', 'warn')
      return
    }
    if (canReach(target, source, edgesRef.current)) {
      showToast('这条连线会形成环，数据只能单向流动', 'warn')
      return
    }
    let next = edgesRef.current
    if ([NODE_CLEAN, NODE_SPLIT, NODE_OUTPUT].includes(targetNode.type)) {
      next = next.filter((edge) => edge.target !== target)
    }
    next = addEdge({
      ...connection,
      id: uid('e'),
      type: 'smoothstep',
      animated: false,
    }, next)
    setEdges(next)
  }, [setEdges, showToast])

  const isValidConnection = useCallback((connection) => {
    const { source, target } = connection
    if (!source || !target || source === target) return false
    const byId = new Map(nodesRef.current.map((node) => [node.id, node]))
    const sourceNode = byId.get(source)
    const targetNode = byId.get(target)
    if (!sourceNode || !targetNode) return false
    if (sourceNode.type === NODE_OUTPUT || sourceNode.type === NODE_SPLIT) return false
    if (targetNode.type === NODE_FILE) return false
    if (targetNode.type === NODE_MERGE && sourceNode.type !== NODE_FILE) return false
    if (edgesRef.current.some((edge) => edge.source === source && edge.target === target)) return false
    return !canReach(target, source, edgesRef.current)
  }, [])

  const addNodeAtPosition = useCallback((type, position, select = true) => {
    const node = makeNode(type, position)
    setNodes((prev) => {
      const cleared = select ? prev.map((item) => ({ ...item, selected: false })) : prev
      return [...cleared, { ...node, selected: select }]
    })
    addLog(`已添加${NODE_META[type]?.label || '节点'}`, 'info')
    return node
  }, [setNodes, addLog])

  const addNodeAtCenter = useCallback((type) => {
    const area = document.querySelector('.canvas-area')
    const rect = area ? area.getBoundingClientRect() : { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight }
    const position = screenToFlowPosition({
      x: rect.left + rect.width / 2 - (NODE_WIDTH[type] || 240) / 2,
      y: rect.top + rect.height / 2 - 80,
    })
    addNodeAtPosition(type, position)
  }, [screenToFlowPosition, addNodeAtPosition])

  const onDrop = useCallback((event) => {
    event.preventDefault()
    event.stopPropagation()
    if (runningRef.current) {
      showToast('运行中不能修改画布', 'warn')
      return
    }
    const type = event.dataTransfer.getData('application/x-pipeline-node')
      || event.dataTransfer.getData('text/plain')
    if (!NODE_META[type]) return
    const position = screenToFlowPosition({ x: event.clientX, y: event.clientY })
    addNodeAtPosition(type, position)
  }, [screenToFlowPosition, addNodeAtPosition, showToast])

  const onDragOver = useCallback((event) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
  }, [])

  const addFiles = useCallback((paths, x, y, nodeId) => {
    const incoming = (Array.isArray(paths) ? paths : []).filter(Boolean).map(String)
    if (!incoming.length) return
    const currentNodes = nodesRef.current
    const currentEdges = edgesRef.current
    const existingPaths = new Set(
      currentNodes.filter((node) => node.type === NODE_FILE && node.data.path)
        .map((node) => String(node.data.path).toLowerCase().replace(/\//g, '\\')),
    )
    const unique = incoming.filter((path) => (
      !existingPaths.has(path.toLowerCase().replace(/\//g, '\\'))
    ))
    const duplicates = incoming.length - unique.length
    if (!unique.length) {
      showToast('这些文件已经在画布上了', 'warn')
      return
    }

    const canDropHere = x !== null && x !== undefined && y !== null && y !== undefined
    let flowPosition = canDropHere
      ? screenToFlowPosition({ x: Number(x), y: Number(y) })
      : screenToFlowPosition({
        x: window.innerWidth / 2,
        y: window.innerHeight / 2,
      })
    if (!flowPosition || !Number.isFinite(flowPosition.x) || !Number.isFinite(flowPosition.y)) {
      flowPosition = { x: 120, y: 120 }
    }

    let hitNode = null
    if (nodeId) {
      hitNode = currentNodes.find((node) => node.id === nodeId && node.type === NODE_FILE)
    }
    if (!hitNode && canDropHere) {
      hitNode = currentNodes.find((node) => {
        if (node.type !== NODE_FILE || node.data.path) return false
        const width = node.measured?.width || node.width || NODE_WIDTH[NODE_FILE]
        const height = node.measured?.height || 190
        return flowPosition.x >= node.position.x
          && flowPosition.x <= node.position.x + width
          && flowPosition.y >= node.position.y
          && flowPosition.y <= node.position.y + height
      }) || null
    }

    const emptyNodes = currentNodes
      .filter((node) => node.type === NODE_FILE && !node.data.path)
      .sort((a, b) => (a.position.y - b.position.y) || (a.position.x - b.position.x))
    const ordered = []
    if (hitNode) ordered.push(hitNode)
    emptyNodes.forEach((node) => {
      if (!ordered.some((item) => item.id === node.id)) ordered.push(node)
    })

    const filled = new Map()
    const newNodes = []
    unique.forEach((path, index) => {
      const target = ordered[index]
      if (target) {
        filled.set(target.id, path)
      } else {
        const offset = index - ordered.length
        newNodes.push(makeNode(NODE_FILE, {
          x: flowPosition.x + Math.max(offset, 0) * 28,
          y: flowPosition.y + Math.max(offset, 0) * 34,
        }, {
          path,
          name: basename(path),
          loading: true,
        }))
      }
    })

    const nextNodes = currentNodes.map((node) => {
      if (!filled.has(node.id)) return node
      const path = filled.get(node.id)
      return {
        ...node,
        data: {
          ...node.data,
          path,
          name: basename(path),
          columns: [],
          rows: [],
          sheets: [],
          loading: true,
          error: '',
          runtime: null,
        },
      }
    }).concat(newNodes)

    let nextEdges = currentEdges
    if (newNodes.length && filled.size) {
      const mergeTargets = new Set()
      currentEdges.forEach((edge) => {
        if (!filled.has(edge.source)) return
        const targetNode = currentNodes.find((node) => node.id === edge.target)
        if (targetNode && targetNode.type === NODE_MERGE) mergeTargets.add(targetNode.id)
      })
      if (mergeTargets.size === 1) {
        const mergeId = [...mergeTargets][0]
        const additions = newNodes.map((node) => makeEdge(node.id, mergeId))
        nextEdges = currentEdges.concat(additions)
      }
    }

    setNodes(nextNodes)
    setEdges(nextEdges)
    call('requestPreviews', JSON.stringify(unique))
    addLog(`已添加 ${unique.length} 个文件到画布`, 'info')
    if (duplicates > 0) showToast(`已跳过 ${duplicates} 个重复文件`, 'warn')
    if (incoming.length > maxFiles) showToast(`一次最多添加 ${maxFiles} 个文件`, 'warn')
  }, [screenToFlowPosition, setNodes, setEdges, addLog, showToast, maxFiles])

  addFilesRef.current = addFiles
  pickFilesRef.current = pickFiles

  /* ------------------------------------------------------------ 运行 */
  const startRun = useCallback(() => {
    if (runningRef.current) return
    if (!bridgeReady || isMock) {
      showToast('桌面桥还没有就绪，无法真正运行流水线', 'error')
      addLog('无法运行：Python 桥未就绪', 'error')
      return
    }
    const check = validateGraph(nodesRef.current, edgesRef.current)
    if (!check.ok) {
      showToast(check.message, 'error')
      addLog(`✗ ${check.message}`, 'error')
      if (check.nodeId) {
        setNodes((prev) => prev.map((node) => (
          node.id === check.nodeId ? { ...node, selected: true } : { ...node, selected: false }
        )))
      }
      return
    }
    const graph = buildRunGraph(nodesRef.current, edgesRef.current, activeTemplate?.name || '')
    setConfigNodeId(null)
    setLogs([])
    setRunSummary(null)
    setShowLogs(false)
    setStopping(false)
    setRunning(true)
    setProgress({ done: 0, total: Math.max(nodesRef.current.length, 1) })
    setNodes((prev) => prev.map((node) => ({
      ...node,
      data: { ...node.data, runtime: { status: 'queued' } },
    })))
    setEdges((prev) => prev.map((edge) => ({
      ...edge,
      animated: true,
      className: 'edge-running',
    })))
    const sent = call('runPipeline', JSON.stringify(graph))
    if (!sent) {
      setRunning(false)
      setNodes((prev) => prev.map((node) => (
        node.data.runtime?.status === 'queued'
          ? { ...node, data: { ...node.data, runtime: null } }
          : node
      )))
      setEdges((prev) => prev.map((edge) => ({ ...edge, animated: false, className: '' })))
      showToast('运行请求没有发送成功', 'error')
    }
  }, [bridgeReady, isMock, activeTemplate, setNodes, setEdges, showToast, addLog])

  const stopRun = useCallback(() => {
    if (!runningRef.current || stopping) return
    setStopping(true)
    addLog('正在停止流水线……', 'warn')
    call('stopPipeline')
  }, [stopping, addLog])

  startRunRef.current = startRun

  const openSave = useCallback(() => {
    if (runningRef.current) {
      showToast('运行中不能保存模板', 'warn')
      return
    }
    if (!nodesRef.current.length) {
      showToast('画布上还没有节点', 'warn')
      return
    }
    setShowSave(true)
  }, [showToast])

  const saveTemplate = useCallback(({ name, description }) => {
    if (!bridgeReady || isMock) {
      showToast('桌面桥还没有就绪，无法保存模板', 'error')
      return
    }
    const graph = buildRunGraph(nodesRef.current, edgesRef.current, name)
    const sent = call('saveTemplate', JSON.stringify({ name, description, graph }))
    setShowSave(false)
    if (!sent) showToast('保存模板请求没有发送成功', 'error')
  }, [bridgeReady, isMock, showToast])

  const requestDeleteTemplate = useCallback((template) => {
    setConfirmState({
      title: '删除模板',
      message: `确定删除自建模板「${template.name}」吗？内置模板不会被删除。`,
      confirmText: '删除模板',
      danger: true,
      onConfirm: () => {
        if (!isMock) call('deleteTemplate', template.id)
        else setTemplates((prev) => prev.filter((item) => item.id !== template.id))
      },
    })
  }, [isMock])

  const pickDirectory = useCallback((current) => new Promise((resolve) => {
    if (!bridgeReady || isMock) {
      resolve('')
      return
    }
    const requestId = `dir-${++dirSeq.current}`
    dirWaiters.current.set(requestId, resolve)
    if (!call('pickOutputDir', requestId, String(current || ''))) {
      dirWaiters.current.delete(requestId)
      resolve('')
      return
    }
    window.setTimeout(() => {
      if (dirWaiters.current.has(requestId)) {
        dirWaiters.current.delete(requestId)
        resolve('')
      }
    }, 120000)
  }), [bridgeReady, isMock])

  /* ------------------------------------------------------------ 事件 */
  const handleEvent = useCallback((event) => {
    const payload = event?.payload || {}
    switch (event?.type) {
      case 'ready': {
        setTemplates(payload.templates || [])
        setOutputDir(payload.outputDir || '')
        setAppVersion(payload.appVersion || '')
        setMaxFiles(Number(payload.maxFiles) || 80)
        setIsMock(Boolean(payload.mock))
        if (!payload.mock) setBridgeReady(true)
        addLog('画布已就绪 · 等待拖入 Excel', 'success')
        if (payload.mock) {
          addLog('浏览器预览模式：未连接 Python 桥，运行与模板功能不可用', 'warn')
        }
        if (!initializedRef.current) {
          initializedRef.current = true
          const list = payload.templates || []
          if (!nodesRef.current.length && list.length) {
            const preferred = list.find((item) => item.id === payload.defaultTemplateId) || list[0]
            window.setTimeout(() => {
              if (!nodesRef.current.length) applyTemplate(preferred, { silent: true })
            }, 40)
          }
        }
        break
      }
      case 'templates': {
        setTemplates(payload.templates || [])
        break
      }
      case 'template-saved': {
        setShowSave(false)
        addLog(`✔ 模板已保存：${payload.name || ''}`, 'success')
        break
      }
      case 'file-preview': {
        const path = payload.path || ''
        setNodes((prev) => prev.map((node) => {
          if (node.type !== NODE_FILE || !samePath(node.data.path, path)) return node
          return {
            ...node,
            data: {
              ...node.data,
              name: node.data.name || basename(path),
              columns: payload.columns || [],
              rows: payload.rows || [],
              sheets: payload.sheets || [],
              loading: false,
              error: payload.error || '',
            },
          }
        }))
        break
      }
      case 'run-start': {
        setRunning(true)
        setStopping(false)
        setRunSummary(null)
        setProgress({ done: 0, total: Number(payload.total) || 0 })
        setNodes((prev) => prev.map((node) => ({
          ...node,
          data: { ...node.data, runtime: { status: 'queued' } },
        })))
        setEdges((prev) => prev.map((edge) => ({
          ...edge,
          animated: true,
          className: 'edge-running',
        })))
        addLog(`▶ 开始运行 ${payload.total || ''} 个节点`, 'info')
        if (payload.ignored) addLog(`ℹ ${payload.ignored} 个未连接节点将被忽略`, 'warn')
        break
      }
      case 'node-start': {
        updateRuntime(payload.nodeId, { status: 'running', startedAt: Date.now() })
        break
      }
      case 'node-progress': {
        updateRuntime(payload.nodeId, {
          status: 'running',
          progress: {
            done: Number(payload.done) || 0,
            total: Number(payload.total) || 0,
            unit: payload.unit || '',
          },
        })
        break
      }
      case 'node-done': {
        const { nodeId, ...rest } = payload
        updateRuntime(nodeId, {
          status: rest.skipped ? 'skipped' : 'done',
          ...rest,
        })
        break
      }
      case 'node-error': {
        updateRuntime(payload.nodeId, {
          status: 'error',
          message: payload.message || '节点执行失败',
        })
        addLog(`✗ ${payload.message || '节点执行失败'}`, 'error')
        if (payload.detail) addLog(`  原因：${payload.detail}`, 'error')
        if (payload.hint) addLog(`  建议：${payload.hint}`, 'error')
        break
      }
      case 'progress': {
        setProgress({
          done: Number(payload.done) || 0,
          total: Number(payload.total) || 0,
        })
        break
      }
      case 'log': {
        addLog(payload.message, payload.level || 'info')
        break
      }
      case 'run-stopping': {
        setStopping(true)
        addLog(payload.message || '正在停止……', 'warn')
        break
      }
      case 'run-done': {
        setRunning(false)
        setStopping(false)
        setRunSummary({ ...payload, ok: true })
        setEdges((prev) => prev.map((edge) => ({ ...edge, animated: false, className: '' })))
        setNodes((prev) => prev.map((node) => {
          const status = node.data.runtime?.status
          if (status === 'running') {
            return { ...node, data: { ...node.data, runtime: { ...node.data.runtime, status: 'done' } } }
          }
          if (status === 'queued') {
            return { ...node, data: { ...node.data, runtime: null } }
          }
          return node
        }))
        addLog(`✔ ${payload.summary || '流水线运行完成'}`, 'success')
        showToast(payload.summary || '流水线运行完成', 'success')
        break
      }
      case 'run-error': {
        setRunning(false)
        setStopping(false)
        setRunSummary({ ...payload, ok: false })
        setShowLogs(true)
        setEdges((prev) => prev.map((edge) => ({ ...edge, animated: false, className: '' })))
        setNodes((prev) => prev.map((node) => {
          const status = node.data.runtime?.status
          if (status === 'queued') return { ...node, data: { ...node.data, runtime: null } }
          return node
        }))
        addLog(`✗ ${payload.message || '流水线运行失败'}`, 'error')
        if (payload.detail) addLog(`  原因：${payload.detail}`, 'error')
        if (payload.hint) addLog(`  建议：${payload.hint}`, 'error')
        showToast(payload.message || '流水线运行失败', 'error')
        break
      }
      case 'run-cancelled': {
        setRunning(false)
        setStopping(false)
        setRunSummary({ ...payload, ok: false, cancelled: true })
        setEdges((prev) => prev.map((edge) => ({ ...edge, animated: false, className: '' })))
        setNodes((prev) => prev.map((node) => {
          const status = node.data.runtime?.status
          if (status === 'running') {
            return { ...node, data: { ...node.data, runtime: { ...node.data.runtime, status: 'idle' } } }
          }
          if (status === 'queued') {
            return { ...node, data: { ...node.data, runtime: null } }
          }
          return node
        }))
        addLog('⏹ 流水线已停止', 'warn')
        showToast('流水线已停止', 'warn')
        break
      }
      case 'output-dir-picked': {
        const waiter = dirWaiters.current.get(payload.requestId)
        if (waiter) {
          dirWaiters.current.delete(payload.requestId)
          waiter(payload.path || '')
        }
        break
      }
      case 'toast': {
        showToast(payload.message || '', payload.level || 'info')
        break
      }
      default:
        break
    }
  }, [addLog, applyTemplate, setNodes, setEdges, showToast, updateRuntime])

  handlersRef.current = handleEvent

  useEffect(() => {
    let disposed = false
    initBridge((event) => {
      if (!disposed) handlersRef.current(event)
    }).then(({ mock }) => {
      if (disposed) return
      if (!mock) setBridgeReady(true)
    })
    return () => { disposed = true }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (new URLSearchParams(window.location.search).get('demo') !== '1') return
    const timer = window.setTimeout(() => {
      const demo = demoGraph()
      setNodes(demo.nodes)
      setEdges(demo.edges)
      setActiveTemplate({ id: 'demo', name: '合并 + 清洗' })
      setProgress({ done: 6, total: 6 })
      setRunSummary({
        ok: true,
        elapsed: 0.2,
        summary: '运行完成：清洗结果_2026-11-23.xlsx（用时 0.2 秒）',
        outputs: [{
          path: 'E:\\python小项目\\excel_workbench_v1.3\\out_put\\清洗结果_2026-11-23.xlsx',
          label: '清洗结果_2026-11-23.xlsx',
          kind: 'file',
        }],
      })
      setBanner('示例管线：3 个销售日报 → 合并 → 清洗 → 输出')
      setLogs([{
        id: 1, time: '16:20:01', level: 'success',
        message: '✔ 流水线运行完成，用时 0.2 秒',
      }])
      const config = new URLSearchParams(window.location.search).get('config')
      if (config === 'merge') setConfigNodeId('merge-1')
      else if (config === 'clean') setConfigNodeId('clean-1')
      else if (config === 'split') setConfigNodeId('split-1')
      else if (config === 'output') setConfigNodeId('output-1')
      else if (config === 'file') setConfigNodeId('file-1')
      window.setTimeout(() => {
        try { fitView({ padding: 0.16, duration: 0 }) } catch (error) { /* ignore */ }
      }, 160)
    }, 500)
    return () => window.clearTimeout(timer)
  }, [fitView, setNodes, setEdges])

  useEffect(() => {
    window.pipelineApp = {
      addFiles: (...args) => addFilesRef.current(...args),
      setDragActive: (value) => setDragActive(Boolean(value)),
    }
    window.__pipelinePick = (id) => pickFilesRef.current(id)
    window.__pipelinePreview = (path) => { if (path) call('openPreview', String(path)) }
    window.__pipelineDebug = {
      getState: () => ({
        nodes: nodesRef.current,
        edges: edgesRef.current,
        running: runningRef.current,
        templates: templatesRef.current,
        progress: progressRef.current,
        logs: logsRef.current,
        runSummary: runSummaryRef.current,
      }),
      run: () => startRunRef.current(),
      applyTemplate: (id) => {
        const template = templatesRef.current.find((item) => item.id === id)
        if (template) applyTemplateRef.current(template)
      },
    }
    const pending = window.__pipelinePending || []
    window.__pipelinePending = []
    pending.forEach((args) => addFilesRef.current(...args))
    return () => {
      delete window.pipelineApp
      delete window.__pipelinePick
      delete window.__pipelinePreview
      delete window.__pipelineDebug
    }
  }, [])

  useEffect(() => {
    const onKey = (event) => {
      const ctrl = event.ctrlKey || event.metaKey
      if (ctrl && event.key === 'Enter') {
        event.preventDefault()
        startRunRef.current()
      }
      // 不占用 Ctrl+S：主窗口的「方案另存」使用该快捷键，
      // 模板保存请点顶部「保存模板」按钮。
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  /* ------------------------------------------------------------ 派生数据 */
  const configNode = useMemo(
    () => nodes.find((node) => node.id === configNodeId) || null,
    [nodes, configNodeId],
  )
  const lastLog = logs.length ? logs[logs.length - 1] : null
  const progressPct = progress.total
    ? Math.min(100, Math.round((progress.done / progress.total) * 100))
    : (running ? 6 : 0)
  const totalFiles = useMemo(() => (
    collectFileNodes(nodes).filter((node) => node.data.path).length
  ), [nodes])
  const actions = useMemo(() => ({
    openConfig, deleteNode, pickFiles, openPath, toast: showToast,
  }), [openConfig, deleteNode, pickFiles, openPath, showToast])

  const defaultTemplateName = useMemo(() => {
    const suffix = new Date().toLocaleDateString('zh-CN').replace(/\//g, '-')
    return `${activeTemplate?.name || '我的流水线'} ${suffix}`
  }, [activeTemplate])

  const builtinMerge = templates.find((template) => template.id === 'builtin_merge')
  const builtinClean = templates.find((template) => template.id === 'builtin_merge_clean')

  return (
    <PipelineContext.Provider value={actions}>
      <div className="app">
        <aside className="palette">
          <div className="palette-brand">
            <span className="brand-mark"><FlowIcon size={19} /></span>
            <span className="palette-brand-text">节点库</span>
          </div>
          <div className="palette-hint">拖到画布，或双击添加</div>
          <div className="palette-list">
            {NODE_TYPES.map((type) => {
              const meta = NODE_META[type]
              const Icon = PALETTE_ICONS[type]
              return (
                <div
                  key={type}
                  className={`palette-item tone-${meta.tone}`}
                  draggable
                  title={meta.tip}
                  onDragStart={(event) => {
                    event.dataTransfer.setData('application/x-pipeline-node', type)
                    event.dataTransfer.setData('text/plain', type)
                    event.dataTransfer.effectAllowed = 'copy'
                  }}
                  onDoubleClick={() => addNodeAtCenter(type)}
                >
                  <span className="palette-icon"><Icon size={16} /></span>
                  <span className="palette-text">
                    <b>{meta.label}</b>
                    <small>{meta.description}</small>
                  </span>
                  <GripIcon size={13} className="palette-grip" />
                </div>
              )
            })}
          </div>
          <div className="palette-foot">
            <span className="dot" /> 所有处理都在本机完成
          </div>
        </aside>

        <main className="workspace">
          <header className="toolbar">
            <div className="toolbar-title">
              <span className="toolbar-mark"><FlowIcon size={18} /></span>
              <div>
                <div className="toolbar-title-text">流水线画布</div>
                <div className="toolbar-sub">PIPELINE STUDIO{appVersion ? ` · v${appVersion}` : ''}</div>
              </div>
            </div>
            {activeTemplate && (
              <span className="active-template-chip" title="当前模板">
                <TemplateIcon size={13} />
                {activeTemplate.name}
              </span>
            )}
            <div className="toolbar-spacer" />
            <span className="canvas-stat">{nodes.length} 节点 · {edges.length} 连线 · {totalFiles} 文件</span>
            <button type="button" className="btn btn-ghost" onClick={() => pickFiles('')} disabled={running}>
              <PlusIcon size={14} /> 添加文件
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setShowTemplates(true)} disabled={running}>
              <TemplateIcon size={14} /> 模板
            </button>
            <button type="button" className="btn btn-ghost" onClick={openSave} disabled={running || !nodes.length}>
              <SaveIcon size={14} /> 保存模板
            </button>
            <button type="button" className="icon-btn" onClick={() => setShowHelp(true)} title="使用帮助">
              <HelpIcon size={16} />
            </button>
          </header>

          <div className="canvas-area">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              isValidConnection={isValidConnection}
              nodeTypes={nodeTypes}
              onDrop={onDrop}
              onDragOver={onDragOver}
              onNodeDoubleClick={(event, node) => {
                event.preventDefault()
                openConfig(node.id)
              }}
              onNodesDelete={(deleted) => {
                const ids = new Set(deleted.map((node) => node.id))
                setEdges((prev) => prev.filter((edge) => !ids.has(edge.source) && !ids.has(edge.target)))
                if (configNodeId && ids.has(configNodeId)) setConfigNodeId(null)
              }}
              onInit={() => {
                window.setTimeout(() => {
                  try { fitView({ padding: 0.18, duration: 300 }) } catch (error) { /* ignore */ }
                }, 80)
              }}
              fitView
              fitViewOptions={{ padding: 0.18 }}
              minZoom={0.25}
              maxZoom={1.8}
              zoomOnDoubleClick={false}
              deleteKeyCode={['Backspace', 'Delete']}
              defaultEdgeOptions={{
                type: 'smoothstep',
                style: { stroke: '#9db3dc', strokeWidth: 1.8 },
                markerEnd: { type: MarkerType.ArrowClosed, width: 15, height: 15, color: '#9db3dc' },
              }}
              connectionLineStyle={{ stroke: '#5b86ff', strokeWidth: 2, strokeDasharray: '5 4' }}
              proOptions={{ hideAttribution: false }}
            >
              <Background variant={BackgroundVariant.Dots} gap={22} size={1.3} color="rgba(93, 115, 160, 0.18)" />
              <Controls showInteractive={false} position="bottom-right" />
            </ReactFlow>

            {banner && (
              <div className="banner">
                <SparkIcon size={14} />
                <span>{banner}</span>
                <button type="button" className="icon-btn tiny" onClick={() => setBanner('')} title="关闭提示">
                  <CloseIcon size={12} />
                </button>
              </div>
            )}

            {!nodes.length && (
              <div className="empty-state">
                <div className="empty-card">
                  <span className="empty-icon"><UploadIcon size={30} /></span>
                  <h2>把 Excel 拖进画布</h2>
                  <p>每个文件会变成独立节点，自动读取表头；再把节点连起来，点底部运行。</p>
                  <div className="empty-actions">
                    {builtinMerge && (
                      <button type="button" className="btn btn-primary" onClick={() => applyTemplate(builtinMerge)}>
                        <SparkIcon size={14} /> 一键合并模板
                      </button>
                    )}
                    {builtinClean && (
                      <button type="button" className="btn btn-ghost" onClick={() => applyTemplate(builtinClean)}>
                        <CleanIcon size={14} /> 合并 + 清洗
                      </button>
                    )}
                    <button type="button" className="btn btn-ghost" onClick={() => pickFiles('')}>
                      <PlusIcon size={14} /> 选择文件
                    </button>
                  </div>
                  <div className="empty-tip">也可以直接把文件拖到此处 · 支持 .xlsx / .xls / .xlsm</div>
                </div>
              </div>
            )}

            {dragActive && (
              <div className="drag-overlay">
                <div className="drag-card">
                  <span className="drag-icon"><UploadIcon size={30} /></span>
                  <b>松手放入</b>
                  <span>自动生成文件节点并读取表头；空文件卡片会被优先填入</span>
                </div>
              </div>
            )}
          </div>

          {runSummary && (
            <div className={`result-strip ${runSummary.ok ? 'ok' : 'error'}`}>
              <span className="result-icon">
                {runSummary.ok ? <CheckIcon size={16} /> : <AlertIcon size={16} />}
              </span>
              <div className="result-text">
                <b>{runSummary.ok ? '运行完成' : (runSummary.cancelled ? '已停止' : '运行失败')}</b>
                <span>{runSummary.summary || runSummary.message || '请查看运行日志'}</span>
              </div>
              <div className="result-actions">
                {(runSummary.outputs || []).slice(0, 3).map((output) => (
                  <button key={output.path} type="button" className="btn btn-ghost small"
                    onClick={() => openPath(output.path)}>
                    <FolderIcon size={13} /> {output.label || '打开结果'}
                  </button>
                ))}
                {!runSummary.ok && (
                  <button type="button" className="btn btn-ghost small" onClick={() => setShowLogs(true)}>
                    <LogIcon size={13} /> 查看日志
                  </button>
                )}
              </div>
              <button type="button" className="icon-btn tiny" onClick={() => setRunSummary(null)} title="关闭结果">
                <CloseIcon size={13} />
              </button>
            </div>
          )}

          <footer className="runbar">
            <button
              type="button"
              className={`run-btn ${running ? 'stop' : ''}`}
              onClick={running ? stopRun : startRun}
              disabled={stopping || (!running && !nodes.length)}
            >
              {running ? <StopIcon size={16} /> : <PlayIcon size={16} />}
              {running ? (stopping ? '停止中…' : '停止') : '运行'}
            </button>
            <div className="run-progress">
              <div className="run-progress-head">
                <span className="run-status-text">
                  {running
                    ? (stopping ? '正在停止…' : '数据正在节点间流动…')
                    : (runSummary ? (runSummary.ok ? '运行完成' : '运行结束') : '准备就绪')}
                </span>
                <span className="run-count">
                  {progress.total ? `${progress.done} / ${progress.total} 节点` : `${nodes.length} 个节点`}
                </span>
              </div>
              <div className="progress-track">
                <i style={{ width: `${progressPct}%` }} className={running ? 'running' : ''} />
              </div>
              <div className="latest-log" title={lastLog?.message || ''}>
                {lastLog ? lastLog.message : '拖入 Excel 并连接节点后，点「运行」'}
              </div>
            </div>
            <div className="runbar-actions">
              <button type="button" className={`btn btn-ghost ${showLogs ? 'active' : ''}`}
                onClick={() => setShowLogs((value) => !value)}>
                <LogIcon size={14} /> 日志{logs.length ? ` ${logs.length}` : ''}
              </button>
              <button type="button" className="btn btn-ghost" onClick={clearCanvas} disabled={running || !nodes.length}>
                <TrashIcon size={14} /> 清空
              </button>
              <button type="button" className="icon-btn" title="适应画布"
                onClick={() => { try { fitView({ padding: 0.18, duration: 350 }) } catch (error) { /* ignore */ } }}>
                <FitIcon size={15} />
              </button>
            </div>
          </footer>

          <LogDrawer
            open={showLogs}
            logs={logs}
            onClose={() => setShowLogs(false)}
            onClear={() => setLogs([])}
          />
        </main>

        {configNode && (
          <ConfigModal
            node={configNode}
            nodes={nodes}
            edges={edges}
            outputDirDefault={outputDir}
            onClose={() => setConfigNodeId(null)}
            onSave={saveNodeConfig}
            pickDirectory={pickDirectory}
            toast={showToast}
          />
        )}

        {showTemplates && (
          <TemplateDrawer
            templates={templates}
            activeTemplateId={activeTemplate?.id || ''}
            onApply={requestApplyTemplate}
            onRequestDelete={requestDeleteTemplate}
            onClose={() => setShowTemplates(false)}
            running={running}
          />
        )}

        {showSave && (
          <SaveTemplateModal
            defaultName={defaultTemplateName}
            nodeCount={nodes.length}
            onSave={saveTemplate}
            onClose={() => setShowSave(false)}
          />
        )}

        {showHelp && <HelpModal onClose={() => setShowHelp(false)} />}

        {confirmState && (
          <ConfirmModal
            title={confirmState.title}
            message={confirmState.message}
            confirmText={confirmState.confirmText}
            danger={confirmState.danger}
            onConfirm={confirmState.onConfirm}
            onClose={() => setConfirmState(null)}
          />
        )}

        <Toast toast={toast} />
      </div>
    </PipelineContext.Provider>
  )
}
