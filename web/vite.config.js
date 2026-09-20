import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// No router, no state library, no backend. The only thing worth configuring is
// that Pyodide's own files are left alone: they are staged into public/ by
// scripts/stage-pyodide.mjs and loaded at runtime by URL, so nothing in them
// should be bundled, pre-transformed or hashed.
//
// The one function the site has -- netlify/functions/ask.mjs, the stateless
// model proxy -- is mounted into the dev server at the path Netlify serves it
// from, so `npm run dev` with ANTHROPIC_API_KEY in the environment is the
// whole local story. Without the key the function answers its probe with
// `live: false` and the page stays in replay, which is what a cold visit to
// the public URL gets when the daily budget is spent.
function askFunction() {
  return {
    name: "workbench-ask-function",
    configureServer(server) {
      server.middlewares.use("/.netlify/functions/ask", async (req, res) => {
        try {
          const { default: handler } = await server.ssrLoadModule("./netlify/functions/ask.mjs");
          const chunks = [];
          for await (const chunk of req) chunks.push(chunk);
          const url = new URL(req.url || "/", "http://localhost");
          const request = new Request(url, {
            method: req.method,
            headers: req.headers,
            body: req.method === "GET" || req.method === "HEAD" ? undefined : Buffer.concat(chunks),
          });
          const response = await handler(request, { ip: req.socket.remoteAddress });
          res.statusCode = response.status;
          response.headers.forEach((v, k) => res.setHeader(k, v));
          if (!response.body) { res.end(); return; }
          const reader = response.body.getReader();
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            res.write(value);
          }
          res.end();
        } catch (err) {
          res.statusCode = 500;
          res.setHeader("content-type", "application/json");
          res.end(JSON.stringify({ error: String(err.message || err) }));
        }
      });
    },
  };
}

export default defineConfig(({ mode }) => {
  // The function's secrets, from web/.env.local (gitignored) or the shell.
  // They go into the dev server's own process for the function to read and
  // nowhere else: Vite exposes only VITE_-prefixed variables to the page, and
  // none of these are.
  const env = loadEnv(mode, process.cwd(), "");
  for (const key of ["ANTHROPIC_API_KEY", "WORKBENCH_DAILY_CAP_USD", "WORKBENCH_IP_CAP",
                     "WORKBENCH_SIGNING_SECRET"]) {
    if (env[key] && !process.env[key]) process.env[key] = env[key];
  }
  return {
    plugins: [react(), askFunction()],
    build: { target: "es2022", chunkSizeWarningLimit: 900 },
    optimizeDeps: { exclude: ["pyodide"] },
    server: { fs: { strict: false } },
  };
});
