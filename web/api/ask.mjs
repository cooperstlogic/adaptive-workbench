// The site's one function, at the path the page calls: /api/ask.
//
// Vercel builds every file under api/ into a function, so this directory
// holds one file and the function itself lives in web/function/, where the
// dev server (vite.config.js) and the harness (scripts/ask-check.mjs,
// scripts/pyodide-check.mjs) import it without going through the host.
export { GET, POST } from "../function/ask.mjs";
