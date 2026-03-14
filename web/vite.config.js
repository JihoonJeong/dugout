import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/dugout/',
  server: {
    proxy: {
      '/game': 'http://localhost:8000',
      '/health': 'http://localhost:8000',
      '/daily': 'http://localhost:8000',
      '/advisor': 'http://localhost:8000',
    },
  },
})
