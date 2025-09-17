import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  appType: 'spa',
  root: '.',
  base: '/',
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    open: false,
    proxy: {
      // Frontend will call /api/...  -> this proxies to the backend during dev
      '/api': {
        target: 'http://127.0.0.1:8000',   // <— change if your FastAPI port differs
        changeOrigin: true,
        // If your backend is mounted at root (most FastAPI apps), keep rewrite:
        //rewrite: (path) => path.replace(/^\/api/, ''),
        // If your FastAPI is mounted under /api already, comment the line above.
      }
    }
  }
});
