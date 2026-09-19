import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// No router, no state library, no backend. The only thing worth configuring is
// that Pyodide's own files are left alone: they are staged into public/ by
// scripts/stage-pyodide.mjs and loaded at runtime by URL, so nothing in them
// should be bundled, pre-transformed or hashed.
export default defineConfig({
  plugins: [react()],
  build: { target: "es2022", chunkSizeWarningLimit: 900 },
  optimizeDeps: { exclude: ["pyodide"] },
  server: { fs: { strict: false } },
});
