import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // Optional same-origin route to the API. Set VITE_API_BASE_URL=/api/v1 to use it
    // and CORS stops mattering entirely.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: { port: 4173, strictPort: true },
})
