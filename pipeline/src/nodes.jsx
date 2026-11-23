import React, { memo } from 'react'
import { Handle, Position, useNodeConnections } from '@xyflow/react'

import { usePipelineActions } from './context'
import {
  NODE_CLEAN, NODE_FILE, NODE_MERGE, NODE_OUTPUT, NODE_SPLIT,
  basename, formatDuration, formatNumber,
} from './graph'
import {
  AlertIcon, CleanIcon, FileIcon, FolderIcon, MergeIcon, OutputIcon,
  SettingsIcon, SplitIcon, TableIcon, TrashIcon, UploadIcon,
} from './icons'

const STATUS_TEXT = {
  empty: '待添加',
  idle: '就绪',
  queued: '排队',
  running: '处理中',
  done: '完成',
  error: '失败',
  skipped: '已跳过',
}

function StatusPill({ status, label }) {
  return (
    <span className={`status-pill status-${status}`}>
      <i />
      {label || STATUS_TEXT[status] || '就绪'}
    </span>
  )
}

function NodeShell({
  id, type, selected, title, subtitle, runtime, children, footer,
  handles = 'both', className = '', hideSettings = false, metrics = null,
}) {
  const actions = usePipelineActions()
  const meta = {
    file: { tone: 'file', icon: FileIcon },
    merge: { tone: 'merge', icon: MergeIcon },
    clean: { tone: 'clean', icon: CleanIcon },
    split: { tone: 'split', icon: SplitIcon },
    output: { tone: 'output', icon: OutputIcon },
  }[type] || { tone: 'file', icon: FileIcon }
  const Icon = meta.icon
  const status = runtime?.status || 'idle'

  return (
    <div
      className={`node-card tone-${meta.tone} status-${status} ${selected ? 'selected' : ''} ${className}`}
      data-node-id={id}
      data-node-type={type}
    >
      {handles !== 'source-only' && (
        <Handle type="target" position={Position.Left} className="pipeline-handle handle-target" />
      )}
      {handles !== 'target-only' && (
        <Handle type="source" position={Position.Right} className="pipeline-handle handle-source" />
      )}

      <div className="node-head">
        <span className="node-icon"><Icon size={17} /></span>
        <div className="node-heading">
          <div className="node-title" title={title}>{title}</div>
          {subtitle && <div className="node-subtitle" title={subtitle}>{subtitle}</div>}
        </div>
        <StatusPill status={status} />
        <div className="node-actions nodrag nopan">
          {!hideSettings && (
            <button
              type="button"
              className="node-action"
              title="设置节点（也可双击卡片）"
              onClick={(event) => {
                event.stopPropagation()
                actions.openConfig(id)
              }}
            >
              <SettingsIcon size={13} />
            </button>
          )}
          <button
            type="button"
            className="node-action danger"
            title="删除节点"
            onClick={(event) => {
              event.stopPropagation()
              actions.deleteNode(id)
            }}
          >
            <TrashIcon size={13} />
          </button>
        </div>
      </div>

      <div className="node-body">
        {children}
        {status === 'running' && runtime?.progress && (
          <div className="node-progress">
            <div className="node-progress-meta">
              <span>{runtime.progress.unit === 'files' ? '文件' : '进度'}</span>
              <span>{runtime.progress.done}/{runtime.progress.total}</span>
            </div>
            <div className="node-progress-track">
              <i style={{ width: `${Math.min(100, Math.round((runtime.progress.done / Math.max(runtime.progress.total, 1)) * 100))}%` }} />
            </div>
          </div>
        )}
      </div>

      {footer && <div className="node-footer">{footer}</div>}
      {metrics && <div className="node-metrics">{metrics}</div>}
    </div>
  )
}

function MiniTable({ columns = [], rows = [], loading = false, emptyText = '等待表头预览' }) {
  if (loading) {
    return (
      <div className="mini-table-skeleton">
        <div /><div /><div />
      </div>
    )
  }
  if (!columns.length) {
    return <div className="mini-table-empty">{emptyText}</div>
  }
  const visible = columns.slice(0, 4)
  const more = columns.length - visible.length
  return (
    <div className="mini-table-wrap">
      <table className="mini-table">
        <colgroup>
          {visible.map((column, index) => (
            <col key={`c-${index}`} style={{ width: index === 0 ? '34%' : `${66 / Math.max(visible.length - 1, 1)}%` }} />
          ))}
          {more > 0 && <col style={{ width: '22px' }} />}
        </colgroup>
        <thead>
          <tr>
            {visible.map((column, index) => (
              <th key={`h-${index}`} title={String(column)}>{String(column)}</th>
            ))}
            {more > 0 && <th className="more">+{more}</th>}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 3).map((row, rowIndex) => (
            <tr key={`r-${rowIndex}`}>
              {visible.map((_, columnIndex) => (
                <td key={`d-${rowIndex}-${columnIndex}`} title={String(row[columnIndex] ?? '')}>
                  {String(row[columnIndex] ?? '')}
                </td>
              ))}
              {more > 0 && <td className="more">…</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FileNodeInner({ id, data, selected }) {
  const actions = usePipelineActions()
  const runtime = data.runtime || null
  const hasFile = Boolean(data.path)
  const columns = Array.isArray(data.columns) ? data.columns : []
  const rows = Array.isArray(data.rows) ? data.rows : []
  const sheets = Array.isArray(data.sheets) ? data.sheets : []
  const loading = Boolean(data.loading)
  const error = String(data.error || '')
  const status = runtime?.status || (hasFile ? 'idle' : 'empty')

  const title = hasFile ? (data.name || basename(data.path)) : '拖入 Excel 文件'
  const subtitle = hasFile ? data.path : '或点击下方选择文件'

  const footer = hasFile ? (
    <>
      <span className="footer-left">
        <TableIcon size={12} />
        {columns.length ? `${formatNumber(columns.length)} 列` : '读取中'}
        {sheets.length > 0 ? ` · ${sheets.length} 个工作表` : ''}
      </span>
      <span className="footer-right">
        {runtime?.rows != null ? `${formatNumber(runtime.rows)} 行` : (rows.length ? `预览 ${rows.length} 行` : '')}
      </span>
    </>
  ) : (
    <>
      <span className="footer-left">支持 .xlsx / .xls / .xlsm</span>
      <span className="footer-right">拖入即生成预览</span>
    </>
  )

  return (
    <NodeShell
      id={id}
      type={NODE_FILE}
      selected={selected}
      title={title}
      subtitle={subtitle}
      runtime={{ ...(runtime || {}), status }}
      handles="source-only"
      footer={footer}
      className="file-node"
    >
      {!hasFile ? (
        <button
          type="button"
          className="nodrag file-placeholder"
          onClick={(event) => {
            event.stopPropagation()
            actions.pickFiles(id)
          }}
        >
          <span className="upload-badge"><UploadIcon size={20} /></span>
          <span className="placeholder-title">拖入 Excel 文件</span>
          <span className="placeholder-sub">松手后自动生成表头预览</span>
          <span className="placeholder-action">选择文件</span>
        </button>
      ) : (
        <>
          <MiniTable columns={columns} rows={rows} loading={loading} emptyText={error ? '无法读取表头' : '等待表头预览'} />
          {error && (
            <div className="node-error-line" title={error}>
              <AlertIcon size={12} />
              {error}
            </div>
          )}
          {runtime?.status === 'running' && (
            <div className="file-running-hint">正在读取并处理…</div>
          )}
          {runtime?.status === 'done' && runtime?.skipped && (
            <div className="file-running-hint muted">本次跳过（未选择文件）</div>
          )}
        </>
      )}
    </NodeShell>
  )
}

function MergeNodeInner({ id, data, selected }) {
  const connections = useNodeConnections({ handleType: 'target' })
  const runtime = data.runtime || null
  const inputCount = connections.length
  const chips = [
    data.addSource ? '带来源列' : '不带来源列',
    data.alignment === 'intersection' ? '仅共有列' : '按表头合并',
    data.allSheets ? '全部工作表' : '仅首个工作表',
  ]
  const footer = (
    <>
      <span className="footer-left">输入 {inputCount} 个文件</span>
      <span className="footer-right">
        {runtime?.status === 'done' && runtime.rows != null
          ? `→ ${formatNumber(runtime.rows)} 行`
          : runtime?.status === 'error' ? '失败' : '合成一张总表'}
      </span>
    </>
  )
  return (
    <NodeShell
      id={id}
      type={NODE_MERGE}
      selected={selected}
      title="合并"
      subtitle={inputCount ? `把 ${inputCount} 个文件合成一张表` : '等待连接文件节点'}
      runtime={runtime}
      footer={footer}
    >
      <div className="chip-row">{chips.map((chip) => <span className="chip" key={chip}>{chip}</span>)}</div>
      <div className="node-hint">按表头对齐，缺列自动留空</div>
    </NodeShell>
  )
}

function CleanNodeInner({ id, data, selected }) {
  const runtime = data.runtime || null
  const chips = []
  if (data.removeEmptyRows) chips.push('删空行')
  if (data.removeEmptyCols) chips.push('删空列')
  if (data.stripText) chips.push('去空格')
  if (data.normalizeNumbers) chips.push('数字统一')
  if (data.normalizeDates) chips.push('日期统一')
  if (data.dropDuplicates) chips.push('去重')
  const footer = (
    <>
      <span className="footer-left">内存清洗 · 不改原文件</span>
      <span className="footer-right">
        {runtime?.status === 'done'
          ? `${formatNumber(runtime.inRows)} → ${formatNumber(runtime.outRows)} 行`
          : runtime?.status === 'error' ? '失败' : '格式统一'}
      </span>
    </>
  )
  return (
    <NodeShell
      id={id}
      type={NODE_CLEAN}
      selected={selected}
      title="清洗"
      subtitle="去空行、统一数字与日期"
      runtime={runtime}
      footer={footer}
    >
      <div className="chip-row">
        {chips.length ? chips.map((chip) => <span className="chip" key={chip}>{chip}</span>)
          : <span className="chip muted">未启用规则</span>}
      </div>
    </NodeShell>
  )
}

function SplitNodeInner({ id, data, selected }) {
  const actions = usePipelineActions()
  const runtime = data.runtime || null
  const column = String(data.column || '').trim()
  const footer = (
    <>
      <span className="footer-left">
        {runtime?.status === 'done' ? `生成 ${formatNumber(runtime.files)} 个文件` : '直接输出多个文件'}
      </span>
      {runtime?.status === 'done' && runtime.output ? (
        <button
          type="button"
          className="nodrag footer-link"
          onClick={(event) => { event.stopPropagation(); actions.openPath(runtime.output) }}
        >
          <FolderIcon size={12} /> 打开
        </button>
      ) : (
        <span className="footer-right">{column ? `按「${column}」` : '未选拆分列'}</span>
      )}
    </>
  )
  return (
    <NodeShell
      id={id}
      type={NODE_SPLIT}
      selected={selected}
      title="拆分"
      subtitle={column ? `按「${column}」分组输出` : '双击选择拆分列'}
      runtime={runtime}
      handles="target-only"
      footer={footer}
    >
      <div className="chip-row">
        <span className="chip">{data.mode === 'sheet' ? '每个源表一个文件' : '每个分组一个文件'}</span>
        {data.skipEmpty && <span className="chip">过滤空分组</span>}
      </div>
    </NodeShell>
  )
}

function OutputNodeInner({ id, data, selected }) {
  const actions = usePipelineActions()
  const runtime = data.runtime || null
  const fileName = String(data.fileName || '流水线结果.xlsx')
  const folder = String(data.outputDir || '').trim()
  const footer = (
    <>
      <span className="footer-left">
        {runtime?.status === 'done' ? `已保存 · ${formatNumber(runtime.rows)} 行` : (folder ? basename(folder) : '默认输出到 out_put')}
      </span>
      {runtime?.status === 'done' && runtime.output ? (
        <button
          type="button"
          className="nodrag footer-link"
          onClick={(event) => { event.stopPropagation(); actions.openPath(runtime.output) }}
        >
          <FolderIcon size={12} /> 打开
        </button>
      ) : (
        <span className="footer-right">{data.autoRename ? '自动避让重名' : '允许覆盖'}</span>
      )}
    </>
  )
  return (
    <NodeShell
      id={id}
      type={NODE_OUTPUT}
      selected={selected}
      title="输出"
      subtitle={fileName}
      runtime={runtime}
      handles="target-only"
      footer={footer}
    >
      <div className="chip-row">
        <span className="chip">{fileName.toLowerCase().endsWith('.xlsx') ? 'Excel 结果' : '自动补 .xlsx'}</span>
        {runtime?.status === 'done' && runtime.ms != null && (
          <span className="chip muted">{formatDuration(runtime.ms)}</span>
        )}
      </div>
    </NodeShell>
  )
}

export const nodeTypes = {
  [NODE_FILE]: memo(FileNodeInner),
  [NODE_MERGE]: memo(MergeNodeInner),
  [NODE_CLEAN]: memo(CleanNodeInner),
  [NODE_SPLIT]: memo(SplitNodeInner),
  [NODE_OUTPUT]: memo(OutputNodeInner),
}
