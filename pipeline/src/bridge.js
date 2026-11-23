let handlers = { onEvent: () => {} }
let channelObject = null
let mockMode = false

/**
 * 初始化 QWebChannel。必须在 Canvas 组件挂载后调用，
 * Python 侧收到 ready() 后会推送模板与实际输出目录。
 */
export function initBridge(onEvent) {
  handlers.onEvent = typeof onEvent === 'function' ? onEvent : () => {}
  return new Promise((resolve) => {
    const transport = window.qt && window.qt.webChannelTransport
    if (!transport || typeof window.QWebChannel === 'undefined') {
      mockMode = true
      console.warn('[pipeline] QWebChannel 不可用，进入浏览器预览模式')
      window.pipelineMock = {
        emit: (event) => handlers.onEvent(event),
      }
      window.setTimeout(() => {
        handlers.onEvent({
          type: 'ready',
          payload: {
            appVersion: '1.3.0',
            outputDir: '',
            templates: [],
            defaultTemplateId: '',
            maxFiles: 80,
            mock: true,
          },
        })
      }, 60)
      resolve({ mock: true })
      return
    }

    try {
      new window.QWebChannel(transport, (channel) => {
        channelObject = channel.objects && channel.objects.bridge
        if (!channelObject) {
          mockMode = true
          console.warn('[pipeline] 没有找到 bridge 对象')
          resolve({ mock: true })
          return
        }
        channelObject.event.connect((payload) => {
          try {
            const event = JSON.parse(payload)
            if (event && event.type) handlers.onEvent(event)
          } catch (error) {
            console.error('[pipeline] 无法解析 Python 事件', error, payload)
          }
        })
        channelObject.ready()
        resolve({ mock: false })
      })
    } catch (error) {
      mockMode = true
      console.error('[pipeline] QWebChannel 初始化失败', error)
      resolve({ mock: true })
    }
  })
}

export function isMock() {
  return mockMode
}

export function call(method, ...args) {
  if (!channelObject) {
    if (!mockMode) console.warn(`[pipeline] 桥未就绪，忽略 ${method}`)
    return false
  }
  try {
    channelObject[method](...args)
    return true
  } catch (error) {
    console.error(`[pipeline] 调用 ${method} 失败`, error)
    return false
  }
}
