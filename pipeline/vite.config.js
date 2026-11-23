import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 当前 PyQt5 自带 Qt 5.15.2（Chromium 83），构建目标按 chrome83 走，
// 否则 ||=、??= 等 ES2021 语法会在 QWebEngineView 里直接 SyntaxError。
// 产物写入 app/resources/pipeline，由 QWebEngineView 以 file:// 加载。
// 注意：file:// 下 Chromium 对 type="module" 有严格 MIME 检查，
// 因此生产构建输出 IIFE 经典脚本，并在 scripts/classic.mjs 中去掉 type="module"。
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: '../app/resources/pipeline',
    emptyOutDir: true,
    target: 'chrome83',
    cssTarget: 'chrome83',
    sourcemap: false,
    modulePreload: false,
    rollupOptions: {
      output: {
        format: 'iife',
        inlineDynamicImports: true,
        entryFileNames: 'assets/app.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
})
