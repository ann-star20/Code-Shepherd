/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      exclude: ["src/test/**", "src/pages/**/Placeholder.tsx"],
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://api-core:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/kms": {
        target: "http://m0:8002",
        changeOrigin: true,
        bypass: (req) => {
          // text/html 요청(페이지 네비게이션)은 프록시하지 않고 SPA로 서빙
          if (req.headers["accept"]?.includes("text/html")) return req.url;
        },
      },
      "/hitl": {
        target: "http://m0:8002",
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers["accept"]?.includes("text/html")) return req.url;
        },
      },
      "/chat": {
        target: "http://m0:8002",
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers["accept"]?.includes("text/html")) return req.url;
        },
      },
    },
  },
});
