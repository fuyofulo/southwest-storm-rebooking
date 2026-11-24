import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The page calls the rebooking service through /api, proxied to the FastAPI app.
// Set API_URL to point somewhere other than the default local service.
const api = process.env.API_URL || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: api, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, '') },
    },
  },
})
