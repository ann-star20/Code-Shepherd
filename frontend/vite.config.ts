/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
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
    watch: {
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      "/api": {
        // 로컬 풀스택은 VITE_PROXY_TARGET=http://localhost:8000 로 덮어쓴다(기본은 compose 호스트).
        target: process.env.VITE_PROXY_TARGET ?? "http://api-core:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/kms": {
        target: process.env.VITE_M0_PROXY_TARGET ?? "http://m0:8002",
        changeOrigin: true,
        bypass: (req) => {
          // text/html 요청(페이지 네비게이션)은 프록시하지 않고 SPA로 서빙
          if (req.headers["accept"]?.includes("text/html")) return req.url;
        },
      },
      "/hitl": {
        target: process.env.VITE_M0_PROXY_TARGET ?? "http://m0:8002",
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers["accept"]?.includes("text/html")) return req.url;
        },
      },
      "/chat": {
        target: process.env.VITE_M0_PROXY_TARGET ?? "http://m0:8002",
        changeOrigin: true,
        bypass: (req) => {
          if (req.headers["accept"]?.includes("text/html")) return req.url;
        },
      },
      // m3 리뷰 결과 조회 — GET /review/{owner}/{repo}/{pr}. m3는 8004 포트.
      // 로컬 풀스택은 VITE_M3_PROXY_TARGET=http://localhost:8004 로 덮어쓴다(기본은 compose 호스트).
      // TODO(prod): 프로덕션은 게이트웨이/인그레스에서 m3 라우팅을 처리 — 이 프록시는 로컬 dev 전용.
      "/m3-api": {
        target: process.env.VITE_M3_PROXY_TARGET ?? "http://m3:8004",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/m3-api/, ""),
      },
      "/m6-api": {
        target: process.env.VITE_M6_PROXY_TARGET ?? "http://m6:8007",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/m6-api/, ""),
      },
      "/m2-api": {
        target: process.env.VITE_M2_PROXY_TARGET ?? "http://m2:8003",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/m2-api/, ""),
      },
    },
  },
});
