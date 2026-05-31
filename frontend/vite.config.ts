import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev proxy forwards API + health checks to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/v1': 'http://localhost:8000',
      '/healthz': 'http://localhost:8000',
    },
  },
})
