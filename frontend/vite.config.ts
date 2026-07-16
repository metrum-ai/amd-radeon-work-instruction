// Copyright Advanced Micro Devices, Inc.
//
// SPDX-License-Identifier: MIT

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      // Backend REST + SSE (e.g. /api/v1/machine-stream). `ws: true` and no
      // buffering keep the event stream flowing under `npm run dev`.
      '/api': { target: 'http://localhost:8000', changeOrigin: true, ws: true },
      // Served OEM manual PDFs.
      '/manuals': { target: 'http://localhost:8000', changeOrigin: true },
      '/prometheus': { target: 'http://localhost:9090', rewrite: (p) => p.replace(/^\/prometheus/, '') },
    },
  },
})
