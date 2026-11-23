import React, { useEffect, useMemo, useRef, useState } from 'react'

import {
  NODE_CLEAN, NODE_FILE, NODE_MERGE, NODE_OUTPUT, NODE_SPLIT,
  NODE_META, basename, formatNumber, upstreamColumns,
} from './graph'
import {
  AlertIcon, CheckIcon, CleanIcon, CloseIcon, EyeIcon, FileIcon,
  FolderIcon, HelpIcon, MergeIcon, OutputIcon, SaveIcon, SparkIcon,
  SplitIcon, TemplateIcon, TrashIcon, UploadIcon,
} from './icons'

/* ------------------------------------------------------------------ 基础壳 */
function ModalShell({ title, subtitle, icon, children, footer, onClose, width, className = '' }) {
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose?.() }}>
      <div className={`modal ${className}`} style={width ? { width } : undefined} role="dialog" aria-modal="true">
        <div className="modal-head">
          {icon && <span className="modal-icon">{icon}</span>}
          <div className="modal-heading">
            <div className="modal-title">{title}</div>
            {subtitle && <div className="modal-subtitle">{subtitle}</div>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} title="关闭"><CloseIcon size={16} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

function DrawerShell({ title, subtitle, icon, children, footer, onClose, width }) {
  useEffect(() => {
    const onKey = (event) => {
      if (event.key === 'Escape') onClose?.()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="overlay drawer-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose?.() }}>
      <div className="drawer" style={width ? { width } : undefined} role="dialog" aria-modal="true">
        <div className="drawer-head">
          {icon && <span className="modal-icon">{icon}</span>}
          <div className="modal-heading">
            <div className="modal-title">{title}</div>
            {subtitle && <div className="modal-subtitle">{subtitle}</div>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} title="关闭"><CloseIcon size={16} /></button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </div>
    </div>
  )
}

function Field({ label, hint, children, className = '' }) {
  return (
    <div className={`field ${className}`}>
      {label && <div className="field-label">{label}</div>}
      {children}
      {hint && <div className="field-hint">{hint}</div>}
    </div>
  )
}

function SwitchRow({ checked, onChange, title, description, disabled = false }) {
  return (
    <label className={`switch-row ${checked ? 'on' : ''} ${disabled ? 'disabled' : ''}`}>
      <span className="switch-text">
        <span className="switch-title">{title}</span>
        {description && <span className="switch-desc">{description}</span>}
      </span>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange?.(event.target.checked)}
      />
      <span className="switch-track"><i /></span>
    </label>
  )
}

function Segmented({ value, options, onChange }) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          className={value === option.value ? 'active' : ''}
          onClick={() => onChange?.(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

function PreviewTable({ columns = [], rows = [], maxColumns = 7, maxRows = 5 }) {
  if (!columns.length) {
    return <div className="preview-empty">还没有表头预览。选择文件后会自动读取前几行。</div>
  }
  const visible = columns.slice(0, maxColumns)
  const more = columns.length - visible.length
  return (
    <div className="preview-table-wrap">
      <table className="preview-table">
        <thead>
          <tr>
            {visible.map((column, index) => <th key={`h-${index}`}>{String(column)}</th>)}
            {more > 0 && <th className="more">+{more}</th>}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, maxRows).map((row, rowIndex) => (
            <tr key={`r-${rowIndex}`}>
              {visible.map((_, columnIndex) => <td key={`d-${rowIndex}-${columnIndex}`}>{String(row[columnIndex] ?? '')}</td>)}
              {more > 0 && <td className="more">…</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ------------------------------------------------------------------ 节点参数 */
function extractForm(node) {
  const data = node?.data || {}
  if (!node || node.type === NODE_FILE) return {}
  const form = { ...data }
  delete form.runtime
  delete form.columns
  delete form.rows
  delete form.sheets
  delete form.loading
  delete form.error
  delete form.path
  delete form.name
  return form
}

function normalizePatch(type, form) {
  const clean = { ...form }
  Object.keys(clean).forEach((key) => {
    if (typeof clean[key] === 'string') clean[key] = clean[key].trim()
  })
  if (type === NODE_MERGE) {
    clean.sourceColumn = clean.sourceColumn || '来源文件'
    clean.sheetColumn = clean.sheetColumn || '来源工作表'
    clean.sortColumns = clean.sortColumns || ''
  }
  if (type === NODE_CLEAN) {
    clean.dateFormat = clean.dateFormat || '%Y-%m-%d'
  }
  if (type === NODE_SPLIT) {
    clean.filenameTemplate = clean.filenameTemplate || '{分组列值}.xlsx'
  }
  if (type === NODE_OUTPUT) {
    clean.fileName = clean.fileName || '流水线结果_{日期}.xlsx'
  }
  return clean
}

function validateForm(type, form) {
  if (type === NODE_MERGE) {
    if (form.addSource && !String(form.sourceColumn || '').trim()) {
      return '开启「添加来源列」后，来源文件列名不能为空。'
    }
    if (form.addSource && form.allSheets
      && String(form.sourceColumn || '').trim() === String(form.sheetColumn || '').trim()) {
      return '来源文件列与来源工作表列不能同名。'
    }
  }
  if (type === NODE_CLEAN && form.normalizeDates && !String(form.dateFormat || '').trim()) {
    return '日期格式不能为空，例如 %Y-%m-%d。'
  }
  if (type === NODE_SPLIT) {
    if (!String(form.column || '').trim()) return '请选择或输入用于拆分的列名。'
    if (form.mode === 'file' && !String(form.filenameTemplate || '').includes('{分组列值}')) {
      return '文件名模板必须包含 {分组列值}，例如 {分组列值}.xlsx。'
    }
  }
  if (type === NODE_OUTPUT && !String(form.fileName || '').trim()) {
    return '输出文件名不能为空。'
  }
  return ''
}

export function ConfigModal({
  node, nodes, edges, outputDirDefault, onClose, onSave, pickDirectory, toast,
}) {
  const [form, setForm] = useState(() => extractForm(node))
  const [error, setError] = useState('')
  const [browsing, setBrowsing] = useState('')

  useEffect(() => {
    setForm(extractForm(node))
    setError('')
  }, [node?.id])

  const columns = useMemo(
    () => (node ? upstreamColumns(nodes, edges, node.id) : []),
    [node, nodes, edges],
  )

  if (!node) return null
  const type = node.type
  const meta = NODE_META[type] || NODE_META[NODE_FILE]
  const data = node.data || {}
  const update = (patch) => setForm((prev) => ({ ...prev, ...patch }))

  const browse = async (field) => {
    if (!pickDirectory) return
    setBrowsing(field)
    try {
      const path = await pickDirectory(form[field] || '')
      if (path) update({ [field]: path })
    } finally {
      setBrowsing('')
    }
  }

  const submit = () => {
    const message = validateForm(type, form)
    if (message) { setError(message); return }
    onSave(node.id, normalizePatch(type, form))
    onClose()
  }

  const footer = (
    <>
      {error ? <span className="form-error"><AlertIcon size={13} />{error}</span> : <span className="form-hint">修改只影响下次运行</span>}
      <div className="spacer" />
      <button type="button" className="btn btn-ghost" onClick={onClose}>取消</button>
      <button type="button" className="btn btn-primary" onClick={submit}>
        <CheckIcon size={14} /> 保存参数
      </button>
    </>
  )

  const title = type === NODE_FILE ? '文件节点' : `${meta.short}节点参数`
  const subtitle = type === NODE_FILE ? basename(data.path) || '还没有选择文件' : meta.tip
  const icon = type === NODE_FILE ? <FileIcon size={18} />
    : type === NODE_MERGE ? <MergeIcon size={18} />
      : type === NODE_CLEAN ? <CleanIcon size={18} />
        : type === NODE_SPLIT ? <SplitIcon size={18} />
          : <OutputIcon size={18} />

  if (type === NODE_FILE) {
    return (
      <ModalShell
        title={title}
        subtitle={subtitle}
        icon={icon}
        onClose={onClose}
        footer={(
          <>
            <span className="form-hint">文件只读，不会修改原文件</span>
            <div className="spacer" />
            <button type="button" className="btn btn-ghost danger" onClick={() => {
              onSave(node.id, {
                path: '', name: '', columns: [], rows: [], sheets: [],
                loading: false, error: '', runtime: null,
              })
              onClose()
            }}><TrashIcon size={14} /> 清空节点</button>
            <button type="button" className="btn btn-primary" onClick={onClose}>完成</button>
          </>
        )}
      >
        <div className="file-path-box">
          <div className="file-path-icon"><FileIcon size={20} /></div>
          <div className="file-path-text">
            <div className="file-path-name">{data.path ? (data.name || basename(data.path)) : '未选择文件'}</div>
            <div className="file-path-full" title={data.path || ''}>{data.path || '点击下方按钮选择 Excel 文件，或直接拖到卡片上'}</div>
          </div>
        </div>
        <div className="inline-actions">
          <button type="button" className="btn btn-ghost" onClick={() => window.__pipelinePick?.(node.id)}>
            <UploadIcon size={14} /> 选择文件
          </button>
          <button
            type="button"
            className="btn btn-ghost"
            disabled={!data.path}
            onClick={() => window.__pipelinePreview?.(data.path)}
          >
            <EyeIcon size={14} /> 完整预览
          </button>
        </div>
        <div className="field-label" style={{ marginTop: 6 }}>
          表头预览 · {formatNumber((data.columns || []).length)} 列
          {(data.sheets || []).length ? ` · ${data.sheets.length} 个工作表` : ''}
        </div>
        <PreviewTable columns={data.columns || []} rows={data.rows || []} />
        {data.error && <div className="inline-error"><AlertIcon size={13} />{data.error}</div>}
        <div className="modal-note">
          <SparkIcon size={14} />
          <span>把多个文件节点连到合并节点，就能在运行后得到带来源列的总表。</span>
        </div>
      </ModalShell>
    )
  }

  return (
    <ModalShell title={title} subtitle={subtitle} icon={icon} onClose={onClose} footer={footer} width={560}>
      {type === NODE_MERGE && (
        <>
          <SwitchRow
            checked={Boolean(form.addSource)}
            onChange={(value) => update({ addSource: value })}
            title="添加来源列"
            description="在结果首部写明每行来自哪个文件 / 工作表"
          />
          <div className="field-grid">
            <Field label="来源文件列名">
              <input className="input" value={form.sourceColumn || ''} disabled={!form.addSource}
                placeholder="来源文件"
                onChange={(event) => update({ sourceColumn: event.target.value })} />
            </Field>
            <Field label="来源工作表列名">
              <input className="input" value={form.sheetColumn || ''}
                disabled={!form.addSource || !form.allSheets}
                placeholder="来源工作表"
                onChange={(event) => update({ sheetColumn: event.target.value })} />
            </Field>
          </div>
          <Field label="列对齐策略">
            <Segmented
              value={form.alignment === 'intersection' ? 'intersection' : 'union'}
              onChange={(value) => update({ alignment: value })}
              options={[
                { value: 'union', label: '按表头合并（缺列填空）' },
                { value: 'intersection', label: '只保留共有列' },
              ]}
            />
          </Field>
          <SwitchRow
            checked={Boolean(form.allSheets)}
            onChange={(value) => update({ allSheets: value })}
            title="合并每个文件的所有工作表"
            description="关闭后只读取每个文件的第一个工作表"
          />
          <SwitchRow
            checked={Boolean(form.ignoreEmpty)}
            onChange={(value) => update({ ignoreEmpty: value })}
            title="忽略空工作表 / 空数据"
            description="避免空表在结果里留下空白区块"
          />
          <details className="advanced">
            <summary>更多选项 · 排序</summary>
            <Field label="排序依据列" hint="多个列名用逗号分隔；留空则保持文件原顺序">
              <input className="input" value={form.sortColumns || ''}
                placeholder="例如：日期, 部门"
                onChange={(event) => update({ sortColumns: event.target.value })} />
            </Field>
            <Field label="排序方式">
              <Segmented
                value={form.sortAscending === false ? 'desc' : 'asc'}
                onChange={(value) => update({ sortAscending: value === 'asc' })}
                options={[{ value: 'asc', label: '升序' }, { value: 'desc', label: '降序' }]}
              />
            </Field>
          </details>
          <div className="modal-note">
            <MergeIcon size={14} />
            <span>合并节点只接收文件节点的连线；合并结果再接到清洗 / 输出。</span>
          </div>
        </>
      )}

      {type === NODE_CLEAN && (
        <>
          <div className="check-grid">
            {[
              ['removeEmptyRows', '删除空行', '所有单元格都为空的行'],
              ['removeEmptyCols', '删除空列', '整列都没有数据'],
              ['stripText', '去除首尾空格', '清理文本单元格两端空白'],
              ['normalizeNumbers', '数字统一', '去千分位、货币符号并转数值'],
              ['normalizeDates', '日期统一', '识别日期列并统一格式'],
              ['dropDuplicates', '删除重复行', '按全部列判断'],
            ].map(([key, label, description]) => (
              <label key={key} className={`check-card ${form[key] ? 'on' : ''}`}>
                <input type="checkbox" checked={Boolean(form[key])}
                  onChange={(event) => update({ [key]: event.target.checked })} />
                <span>
                  <b>{label}</b>
                  <small>{description}</small>
                </span>
              </label>
            ))}
          </div>
          {form.normalizeDates && (
            <Field label="目标日期格式" hint="使用 Python 日期格式，例如 %Y-%m-%d；无法识别的值会保留原样">
              <input className="input" value={form.dateFormat || ''}
                placeholder="%Y-%m-%d"
                onChange={(event) => update({ dateFormat: event.target.value })} />
            </Field>
          )}
          <div className="modal-note">
            <CleanIcon size={14} />
            <span>清洗在内存中完成，只改变数据流；原始 Excel 不会被修改。</span>
          </div>
        </>
      )}

      {type === NODE_SPLIT && (
        <>
          <Field label="拆分列" hint={columns.length ? `上游文件里找到 ${columns.length} 列，可直接选择` : '上游文件还没有表头预览，也可以手动输入列名'}>
            <input
              className="input"
              list="pipeline-columns"
              value={form.column || ''}
              placeholder="例如：部门"
              onChange={(event) => update({ column: event.target.value })}
            />
            <datalist id="pipeline-columns">
              {columns.map((column) => <option key={column} value={column} />)}
            </datalist>
          </Field>
          <Field label="拆分方式">
            <Segmented
              value={form.mode === 'sheet' ? 'sheet' : 'file'}
              onChange={(value) => update({ mode: value })}
              options={[
                { value: 'file', label: '每个分组一个文件' },
                { value: 'sheet', label: '每个源表一个文件（多 Sheet）' },
              ]}
            />
          </Field>
          {form.mode !== 'sheet' && (
            <Field label="文件名模板" hint="可用占位符：{分组列值}、{原文件名}、{工作表名}；必须包含 {分组列值}">
              <input className="input" value={form.filenameTemplate || ''}
                placeholder="{分组列值}.xlsx"
                onChange={(event) => update({ filenameTemplate: event.target.value })} />
            </Field>
          )}
          <SwitchRow
            checked={Boolean(form.skipEmpty)}
            onChange={(value) => update({ skipEmpty: value })}
            title="过滤空分组"
            description="分组列为空时，不生成对应文件"
          />
          <Field label="输出文件夹" hint={`留空则自动创建：${outputDirDefault || 'out_put'}\\拆分结果_时间戳`}>
            <div className="input-with-button">
              <input className="input" value={form.outputDir || ''}
                placeholder="留空使用默认输出目录"
                onChange={(event) => update({ outputDir: event.target.value })} />
              <button type="button" className="btn btn-ghost" disabled={browsing === 'outputDir'}
                onClick={() => browse('outputDir')}>
                <FolderIcon size={14} /> {browsing === 'outputDir' ? '选择中…' : '浏览'}
              </button>
            </div>
          </Field>
          <div className="modal-note">
            <SplitIcon size={14} />
            <span>拆分节点是管线终点：直接生成多个 Excel，不能再向下连接。</span>
          </div>
        </>
      )}

      {type === NODE_OUTPUT && (
        <>
          <Field label="输出文件名" hint="可用占位符：{日期}、{时间}、{时间戳}；会自动补 .xlsx">
            <input className="input" value={form.fileName || ''}
              placeholder="流水线结果_{日期}.xlsx"
              onChange={(event) => update({ fileName: event.target.value })} />
          </Field>
          <Field label="输出文件夹" hint={`留空则保存到：${outputDirDefault || '项目 out_put 目录'}`}>
            <div className="input-with-button">
              <input className="input" value={form.outputDir || ''}
                placeholder="留空使用默认输出目录"
                onChange={(event) => update({ outputDir: event.target.value })} />
              <button type="button" className="btn btn-ghost" disabled={browsing === 'outputDir'}
                onClick={() => browse('outputDir')}>
                <FolderIcon size={14} /> {browsing === 'outputDir' ? '选择中…' : '浏览'}
              </button>
            </div>
          </Field>
          <SwitchRow
            checked={Boolean(form.autoRename)}
            onChange={(value) => update({ autoRename: value })}
            title="同名文件自动重命名"
            description="避免覆盖已有结果；关闭后同名文件会被覆盖"
          />
          <div className="modal-note">
            <OutputIcon size={14} />
            <span>输出节点是管线终点，保存最终结果后可直接在节点卡片上打开文件夹。</span>
          </div>
        </>
      )}
    </ModalShell>
  )
}

/* ------------------------------------------------------------------ 模板 */
export function TemplateDrawer({
  templates, activeTemplateId, onApply, onRequestDelete, onClose, running,
}) {
  const [tab, setTab] = useState('all')
  const shown = templates.filter((template) => {
    if (tab === 'builtin') return template.builtin
    if (tab === 'mine') return !template.builtin
    return true
  })

  return (
    <DrawerShell
      title="流水线模板"
      subtitle="拖入新文件就能一键运行；模板不保存本地路径"
      icon={<TemplateIcon size={18} />}
      onClose={onClose}
      width={470}
      footer={(
        <>
          <span className="form-hint">内置模板随程序提供，自建模板保存在 config 目录</span>
        </>
      )}
    >
      <div className="drawer-tabs">
        {[
          ['all', `全部 ${templates.length}`],
          ['builtin', '内置'],
          ['mine', '我的'],
        ].map(([value, label]) => (
          <button key={value} type="button" className={tab === value ? 'active' : ''}
            onClick={() => setTab(value)}>{label}</button>
        ))}
      </div>
      <div className="template-list">
        {shown.map((template) => {
          const active = template.id === activeTemplateId
          const count = (template.graph?.nodes || []).length
          const firstType = (template.graph?.nodes || []).find((node) => node.type !== NODE_FILE)?.type
          const Icon = firstType === NODE_MERGE ? MergeIcon
            : firstType === NODE_CLEAN ? CleanIcon
              : firstType === NODE_SPLIT ? SplitIcon : OutputIcon
          return (
            <div key={template.id} className={`template-card ${active ? 'active' : ''}`}>
              <div className={`template-icon tone-${NODE_META[firstType]?.tone || 'merge'}`}>
                <Icon size={20} />
              </div>
              <div className="template-main">
                <div className="template-title">
                  {template.name}
                  {template.builtin
                    ? <span className="badge">内置</span>
                    : <span className="badge mine">我的</span>}
                  {active && <span className="badge active">当前</span>}
                </div>
                <div className="template-desc">{template.description || '自定义流水线模板'}</div>
                <div className="template-meta">{count} 个节点 · 拖入新文件即可运行</div>
              </div>
              <div className="template-actions">
                <button type="button" className="btn btn-primary small" disabled={running}
                  onClick={() => onApply(template)}>使用</button>
                {!template.builtin && (
                  <button type="button" className="icon-btn danger" title="删除模板"
                    onClick={() => onRequestDelete(template)}><TrashIcon size={14} /></button>
                )}
              </div>
            </div>
          )
        })}
        {!shown.length && (
          <div className="drawer-empty">
            <TemplateIcon size={28} />
            <p>还没有自建模板</p>
            <span>编排好流程后点击顶部「保存模板」，下次拖入新文件即可复用。</span>
          </div>
        )}
      </div>
    </DrawerShell>
  )
}

export function SaveTemplateModal({ defaultName, nodeCount, onSave, onClose }) {
  const [name, setName] = useState(defaultName || '')
  const [description, setDescription] = useState('')
  const [error, setError] = useState('')

  const submit = () => {
    const text = name.trim()
    if (!text) { setError('请填写模板名称'); return }
    onSave({ name: text, description: description.trim() })
  }

  return (
    <ModalShell
      title="保存为模板"
      subtitle={`当前画布有 ${nodeCount} 个节点；只保存结构、连线与参数`}
      icon={<SaveIcon size={18} />}
      onClose={onClose}
      width={480}
      footer={(
        <>
          {error ? <span className="form-error"><AlertIcon size={13} />{error}</span> : <span className="form-hint">同名模板会被更新</span>}
          <div className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>取消</button>
          <button type="button" className="btn btn-primary" onClick={submit}><SaveIcon size={14} /> 保存模板</button>
        </>
      )}
    >
      <Field label="模板名称" hint="例如：销售日报合并、部门拆分">
        <input className="input" autoFocus value={name} maxLength={40}
          placeholder="我的流水线"
          onChange={(event) => { setName(event.target.value); setError('') }} />
      </Field>
      <Field label="模板说明（可选）" hint="会显示在模板列表里，方便以后辨认">
        <textarea className="textarea" rows={3} value={description}
          placeholder="例如：三个门店日报 → 合并 → 清洗 → 输出"
          onChange={(event) => setDescription(event.target.value)} />
      </Field>
      <div className="modal-note">
        <SparkIcon size={14} />
        <span>模板会去掉本地文件路径与表头预览，只保留节点位置、连线和参数。</span>
      </div>
    </ModalShell>
  )
}

export function ConfirmModal({ title, message, confirmText, danger, onConfirm, onClose }) {
  return (
    <ModalShell
      title={title}
      icon={danger ? <AlertIcon size={18} /> : <HelpIcon size={18} />}
      onClose={onClose}
      width={440}
      footer={(
        <>
          <div className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>取消</button>
          <button type="button" className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={() => { onConfirm?.(); onClose?.() }}>{confirmText || '确定'}</button>
        </>
      )}
    >
      <p className="confirm-message">{message}</p>
    </ModalShell>
  )
}

export function HelpModal({ onClose }) {
  return (
    <ModalShell
      title="流水线画布怎么用"
      subtitle="拖入文件 → 连线 → 双击改参数 → 运行"
      icon={<HelpIcon size={18} />}
      onClose={onClose}
      width={620}
      footer={(
        <>
          <span className="form-hint">快捷键：Ctrl + Enter 运行画布</span>
          <div className="spacer" />
          <button type="button" className="btn btn-primary" onClick={onClose}>开始编排</button>
        </>
      )}
    >
      <div className="help-steps">
        {[
          ['1', '拖入 Excel', '把文件或文件夹拖进画布，自动生成独立文件节点，并读取表头与首行预览。'],
          ['2', '连接节点', '文件节点 → 合并节点 → 清洗节点 → 输出节点；也可以直接把文件接到清洗 / 拆分 / 输出。'],
          ['3', '调整参数', '双击节点打开少量参数：合并是否带来源列、清洗删不删空行、拆分按哪一列。'],
          ['4', '一键运行', '点底部「运行」，数据沿连线流动，每个节点实时显示处理行数、文件数和耗时。'],
          ['5', '保存模板', '编排好后保存为模板；下次载入模板，把新文件拖到文件卡片上就能直接跑。'],
        ].map(([index, title, text]) => (
          <div className="help-step" key={index}>
            <span className="help-index">{index}</span>
            <div><b>{title}</b><p>{text}</p></div>
          </div>
        ))}
      </div>
      <div className="help-note">
        <FileIcon size={15} />
        支持 .xlsx / .xls / .xlsm。所有读取、合并、清洗、拆分都在本机完成，文件不会上传。
      </div>
    </ModalShell>
  )
}

/* ------------------------------------------------------------------ 日志 / 提示 */
export function LogDrawer({ open, logs, onClose, onClear }) {
  const listRef = useRef(null)
  useEffect(() => {
    if (open && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [logs, open])

  return (
    <div className={`log-drawer ${open ? 'open' : ''}`} aria-hidden={!open}>
      <div className="log-head">
        <span className="log-title">运行日志 <em>{logs.length}</em></span>
        <button type="button" className="log-action" onClick={onClear}>清空</button>
        <button type="button" className="icon-btn light" onClick={onClose} title="收起"><CloseIcon size={14} /></button>
      </div>
      <div className="log-list" ref={listRef}>
        {logs.length === 0 && <div className="log-empty">运行流水线后，这里会实时显示每个节点的处理日志。</div>}
        {logs.map((log) => (
          <div key={log.id} className={`log-line level-${log.level || 'info'}`}>
            <span className="log-time">{log.time}</span>
            <span className="log-text">{log.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Toast({ toast }) {
  if (!toast) return null
  const Icon = toast.level === 'error' ? AlertIcon : toast.level === 'warn' ? AlertIcon : CheckIcon
  return (
    <div key={toast.id} className={`toast toast-${toast.level || 'info'}`}>
      <Icon size={15} />
      <span>{toast.message}</span>
    </div>
  )
}
