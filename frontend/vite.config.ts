import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig(({ mode }) => {
  const localApi = loadEnv(mode, '.', 'VITE_DEV_API_PROXY').VITE_DEV_API_PROXY || 'http://127.0.0.1:8000';
  return {
    plugins: [react()],
    server: { proxy: { '/api': { target: localApi, changeOrigin: true }, '/health': { target: localApi, changeOrigin: true } } },
    test: { environment: 'jsdom', setupFiles: './src/test/setup.ts', globals: true },
  };
});
