import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Hosted by adamOS at /apps/habits/ (the generic L3 deploy target also passes
// --base=/apps/habits/). Local dev proxies /api to a local adamOS gateway.
export default defineConfig({
  base: '/apps/habits/',
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/api': {
        target: process.env.ADAMOS_GATEWAY || 'http://127.0.0.1:5001',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
