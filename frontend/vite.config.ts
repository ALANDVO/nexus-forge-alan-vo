import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API_TARGET = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5123,
    proxy: {
      "/plans": { target: API_TARGET, changeOrigin: true },
      "/tasks": { target: API_TARGET, changeOrigin: true },
      "/results": { target: API_TARGET, changeOrigin: true },
      "/classify": { target: API_TARGET, changeOrigin: true },
      "/health": { target: API_TARGET, changeOrigin: true },
    },
  },
  test: {
    environment: "happy-dom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.{ts,tsx}"],
    exclude: ["**/dist/**", "**/node_modules/**"],
    css: true,
    globals: true,
  },
});