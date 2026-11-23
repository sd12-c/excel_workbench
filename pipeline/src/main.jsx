import React from 'react'
import { createRoot } from 'react-dom/client'
import { ReactFlowProvider } from '@xyflow/react'
import App from './App.jsx'

// Qt 5.15.2 自带 Chromium 83：flex gap 虽然能通过 CSS.supports，
// 但布局阶段并不会生效。加一个类，用 margin 兜底（Edge/新版浏览器不受影响）。
const chromeVersion = Number((navigator.userAgent.match(/Chrome\/(\d+)/) || [])[1] || 0)
if (chromeVersion > 0 && chromeVersion < 84) {
  document.documentElement.classList.add('no-flex-gap')
}

// Python 可能在 React 挂载完成前就调用 addFiles（极快拖放），先排队。
window.__pipelinePending = window.__pipelinePending || []
window.pipelineApp = window.pipelineApp || {
  addFiles: (...args) => window.__pipelinePending.push(args),
  setDragActive: () => {},
}

const container = document.getElementById('root')
const root = createRoot(container)
root.render(
  <ReactFlowProvider>
    <App />
  </ReactFlowProvider>,
)
