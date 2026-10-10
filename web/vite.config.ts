/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const envDir = fileURLToPath(new URL('.', import.meta.url))
  const env = loadEnv(mode, envDir, '')
  const apiProxyTarget =
    env.API_PROXY_TARGET ||
    process.env.API_PROXY_TARGET ||
    'http://localhost:8000'

  return {
    base: '/',
    plugins: [react()],
    server: {
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: 'dist',
      // 'hidden' generates separate .map files on disk but suppresses sourceMappingURL comments,
      // preventing browser DevTools from automatically discovering or serving sourcemaps publicly.
      sourcemap: 'hidden',
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
  }
})
