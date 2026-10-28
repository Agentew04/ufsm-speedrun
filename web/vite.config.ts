import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base './' => o build em dist/ funciona em qualquer subpasta (GitHub Pages etc.)
export default defineConfig({
  base: './',
  plugins: [react()],
  server: { port: 5173 },
  build: { target: 'es2022', chunkSizeWarningLimit: 1400 },
})
