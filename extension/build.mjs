// Hand-rolled multi-config build (no extra dependency): reuses the frontend's Vite.
// Content script, worker and popup are separate IIFE bundles because MV3 content scripts cannot import modules.
import { copyFileSync, mkdirSync, rmSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { build } from '../frontend/node_modules/vite/dist/node/index.js'

const here = dirname(fileURLToPath(import.meta.url))
const dist = resolve(here, 'dist')
rmSync(dist, { recursive: true, force: true })
mkdirSync(dist, { recursive: true })

const entries = { content: 'src/content/index.ts', background: 'src/background/index.ts', popup: 'src/popup/index.ts' }
for (const [name, entry] of Object.entries(entries)) {
  await build({
    configFile: false,
    root: here,
    logLevel: 'warn',
    build: {
      outDir: dist,
      emptyOutDir: false,
      minify: false, // readable, so the unpacked extension can be reviewed
      target: 'chrome120',
      lib: { entry: resolve(here, entry), formats: ['iife'], name: `jh_${name}`, fileName: () => `${name}.js` },
    },
  })
}
copyFileSync(resolve(here, 'manifest.json'), resolve(dist, 'manifest.json'))
copyFileSync(resolve(here, 'src/popup/popup.html'), resolve(dist, 'popup.html'))
console.log('extension built in', dist)
