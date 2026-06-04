/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Docker 환경에서는 API_TARGET=http://api:8001 로 주입됨
// 로컬 직접 실행 시 기본값 http://localhost:8001 사용
const API_TARGET = process.env.API_TARGET ?? "http://localhost:8001"

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/kms":  { target: API_TARGET, changeOrigin: true },
      "/hitl": { target: API_TARGET, changeOrigin: true },
      "/chat": { target: API_TARGET, changeOrigin: true },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      thresholds: { lines: 80 },
    },
  },
})
