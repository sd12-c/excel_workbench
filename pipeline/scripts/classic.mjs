import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const indexFile = path.resolve(here, '..', '..', 'app', 'resources', 'pipeline', 'index.html')

let html = fs.readFileSync(indexFile, 'utf8')
const before = html

// Vite 会给入口脚本加 type="module"；QtWebEngine 的 file:// 页面
// 对 module script 的 MIME 检查非常严格，改成 defer 经典脚本即可。
html = html.replace(
  /<script type="module" crossorigin src="([^"]+)"><\/script>/g,
  '<script defer src="$1"></script>',
)
html = html.replace(
  /<link rel="stylesheet" crossorigin href="([^"]+)">/g,
  '<link rel="stylesheet" href="$1">',
)

if (html === before) {
  console.warn('[pipeline] index.html 没有需要改写的 module script（可能构建格式已变化）')
} else {
  fs.writeFileSync(indexFile, html, 'utf8')
  console.log('[pipeline] 已把入口脚本改写为经典 defer 脚本')
}
