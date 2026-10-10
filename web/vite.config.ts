/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

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
    plugins: [react(), tailwindcss()],
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
      // Sourcemaps disabled to prevent generating .map files that would be synced to S3 and served
      sourcemap: false,
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
    },
  }
})
