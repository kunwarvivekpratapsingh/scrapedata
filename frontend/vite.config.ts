import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        // Disable response buffering so SSE frames stream through immediately.
        // Without this, Vite's http-proxy buffers the response and EventSource
        // never receives any events until the connection closes.
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes, req) => {
            // For SSE endpoints, disable buffering on the proxy response
            if (req.url?.includes('/events')) {
              proxyRes.headers['x-accel-buffering'] = 'no'
              proxyRes.headers['cache-control'] = 'no-cache'
            }
          })
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
