import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

const backend = process.env.KBOS_BACKEND ?? "http://127.0.0.1:7861";

export default defineConfig({
  base: "/admin/",
  plugins: [react(), tailwindcss()],
  build: { chunkSizeWarningLimit: 1200 },
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5180,
    proxy: {
      "/api": backend,
      "/uploads": backend,
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
});
