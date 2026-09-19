// Put the Python runtime on our own origin.
//
// A demo that depends on a third-party CDN and conference wifi at the same
// moment has a coin flip in it. The runtime and the one wheel we need are
// copied into public/pyodide/ and served from the same host as the page, and
// the wheel's sha256 is checked against pyodide's own lock file before it is
// written, so a bad download fails the build rather than the demo.
//
// Only numpy is fetched. `core/` has one dependency and this is where that
// constraint pays for itself: the whole Python side of the site is 13 MB of
// runtime plus one wheel.

import { createHash } from "node:crypto";
import { cp, mkdir, readFile, writeFile, stat } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = dirname(HERE);
const SRC = join(WEB, "node_modules", "pyodide");
const OUT = join(WEB, "public", "pyodide");

const RUNTIME = [
  "pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm",
  "python_stdlib.zip", "pyodide-lock.json",
];
const WHEELS = ["numpy"];

const exists = async (p) => !!(await stat(p).catch(() => null));

const lock = JSON.parse(await readFile(join(SRC, "pyodide-lock.json"), "utf8"));
const version = JSON.parse(await readFile(join(SRC, "package.json"), "utf8")).version;
const base = `https://cdn.jsdelivr.net/pyodide/v${version}/full`;

await mkdir(OUT, { recursive: true });
for (const name of RUNTIME) await cp(join(SRC, name), join(OUT, name));

for (const name of WHEELS) {
  const pkg = lock.packages[name];
  if (!pkg) throw new Error(`pyodide ${version} has no package named ${name}`);
  const dest = join(OUT, pkg.file_name);
  if (await exists(dest)) {
    const have = createHash("sha256").update(await readFile(dest)).digest("hex");
    if (have === pkg.sha256) { console.log(`  ${pkg.file_name}  cached`); continue; }
  }
  const url = `${base}/${pkg.file_name}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} fetching ${url}`);
  const body = Buffer.from(await res.arrayBuffer());
  const got = createHash("sha256").update(body).digest("hex");
  if (got !== pkg.sha256) {
    throw new Error(`${pkg.file_name} hashed ${got}, lock file says ${pkg.sha256}`);
  }
  await writeFile(dest, body);
  console.log(`  ${pkg.file_name}  ${(body.length / 1048576).toFixed(1)} MB, sha verified`);
}

await writeFile(join(OUT, "staged.json"), JSON.stringify({
  pyodide: version,
  python: lock.info.python,
  packages: Object.fromEntries(WHEELS.map((n) => [n, lock.packages[n].version])),
  note: "served from this site's own origin; see scripts/stage-pyodide.mjs",
}, null, 2) + "\n");
console.log(`pyodide ${version} (Python ${lock.info.python}) staged at public/pyodide`);
