import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The interface is a client of the API and nothing more, so in development every /v1 and /health
// call is proxied to the FastAPI process rather than hard-coded to a host. In production both are
// served by that same process, which is why no base URL appears anywhere in the source.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/v1': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Framer Motion is the largest dependency and only the workspace needs it eagerly; keeping
        // it in its own chunk stops the landing page paying for it.
        manualChunks: {
          motion: ['framer-motion'],
          router: ['react-router-dom'],
        },
      },
    },
  },
})
