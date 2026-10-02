import fs from 'node:fs'
import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// `npm run dev` serves /data/* from a report folder written by `honest-agent report`,
// so local development uses real data without copying it into public/ (and the build).
const reportDir = path.resolve(process.env.HONEST_AGENT_REPORT_DIR ?? '../example_project/honest_agent_report')

function devReportData(): Plugin {
  return {
    name: 'honest-agent-dev-report-data',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const file = path.join(reportDir, 'data', path.normalize(req.url ?? '/'))
        if (!file.startsWith(path.join(reportDir, 'data')) || !fs.existsSync(file)) return next()
        res.setHeader('Content-Type', 'application/json')
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), devReportData()],
  // Relative asset URLs, so the built report works from any path it's hosted under.
  base: './',
  build: {
    // Shipped inside the Python package; `honest-agent report` copies it next to the data.
    outDir: '../cli/honest_agent/report_ui',
    emptyOutDir: true,
  },
})
