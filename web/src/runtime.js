// Boot Python in the browser, mount the repository's own files, and keep the
// visitor's progress.
//
// Three rules hold this file together.
//
// **The bundle is mounted, not reimplemented.** Every file under
// public/workbench came out of the repository by `web/bundle.py`, with a
// sha256 per file in the manifest, and is written into Pyodide's filesystem at
// the same path it has in the repo. `core/`, the seven skill scripts and
// `lims.py` then import each other exactly as they do on a laptop.
//
// **Nothing is written back.** The visitor's rounds live in Pyodide's memory
// and in localStorage, and only the files that actually changed are stored —
// the shipped ones are re-fetched. Reset drops the overlay.
//
// **The runtime is ours.** Pyodide and the numpy wheel are served from this
// site's own origin (scripts/stage-pyodide.mjs), so a cold visit needs no
// third-party CDN.

const MOUNT = "/workbench";
const BUNDLE = `${import.meta.env.BASE_URL}workbench`;
const PYODIDE = `${import.meta.env.BASE_URL}pyodide/`;
const OVERLAY_KEY = "workbench.overlay.v1";

let py = null;
let manifest = null;
let shipped = new Map(); // path -> text, as fetched

const textOf = (bytes) => new TextDecoder().decode(bytes);

async function fetchFile(path) {
  const res = await fetch(`${BUNDLE}/${path}`, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${res.status} fetching ${path}`);
  return new Uint8Array(await res.arrayBuffer());
}

function write(path, bytes) {
  const dest = `${MOUNT}/${path}`;
  py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")));
  py.FS.writeFile(dest, bytes);
}

function readOverlay() {
  try {
    const raw = localStorage.getItem(OVERLAY_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (saved.manifest !== manifest.hash) {
      localStorage.removeItem(OVERLAY_KEY);  // a new bundle starts clean
      return null;
    }
    return saved.files;
  } catch {
    return null;
  }
}

export function clearOverlay() {
  try { localStorage.removeItem(OVERLAY_KEY); } catch { /* private window */ }
}

export function saveOverlay() {
  const files = call("dump_state");
  const changed = {};
  for (const [path, text] of Object.entries(files)) {
    if (shipped.get(path) !== text) changed[path] = text;
  }
  try {
    localStorage.setItem(OVERLAY_KEY, JSON.stringify({
      manifest: manifest.hash, at: new Date().toISOString(), files: changed,
    }));
    return { saved: Object.keys(changed).length, error: null };
  } catch (err) {
    return { saved: 0, error: String(err.message || err) };
  }
}

let booting = null;

export function boot(onStep) {
  // StrictMode mounts effects twice in development, and two Pyodide instances
  // is two runtimes racing over one filesystem. One boot, whoever asks.
  if (!booting) booting = bootOnce(onStep);
  return booting;
}

async function bootOnce(onStep) {
  const step = (text) => onStep && onStep(text);

  step("fetching the runtime");
  const { loadPyodide } = await import(/* @vite-ignore */ `${PYODIDE}pyodide.mjs`);
  py = await loadPyodide({ indexURL: PYODIDE, stdout: () => {}, stderr: () => {} });

  step("loading numpy");
  await py.loadPackage("numpy");

  step("mounting the project");
  manifest = await fetch(`${BUNDLE}/manifest.json`, { cache: "no-cache" }).then((r) => r.json());
  py.FS.mkdirTree(MOUNT);
  write("manifest.json", new TextEncoder().encode(JSON.stringify(manifest)));

  const all = [...manifest.code, ...manifest.state, ...manifest.reference];
  const bytes = await Promise.all(all.map((e) => fetchFile(e.path)));
  all.forEach((entry, i) => {
    write(entry.path, bytes[i]);
    if (!entry.path.endsWith(".whl")) shipped.set(entry.path, textOf(bytes[i]));
  });
  py.FS.mkdirTree(`${MOUNT}/session`);

  const overlay = readOverlay();
  if (overlay) {
    step("restoring your rounds");
    const enc = new TextEncoder();
    for (const [path, text] of Object.entries(overlay)) write(path, enc.encode(text));
  }

  step("starting the driver");
  py.runPython(`import sys\nsys.path.insert(0, ${JSON.stringify(MOUNT)})\nimport wb_driver`);

  return {
    resumed: !!overlay,
    manifest,
    python: py.runPython("import sys; '%d.%d.%d' % sys.version_info[:3]"),
    numpy: py.runPython("import numpy; numpy.__version__"),
    pyodide: py.version,
  };
}

// One calling convention, matching wb_driver.call on the other side.
export function call(name, args = {}) {
  const raw = py.runPython(
    `wb_driver.call(${JSON.stringify(name)}, ${JSON.stringify(JSON.stringify(args))})`);
  const out = JSON.parse(raw);
  if (!out.ok) {
    const err = new Error(out.error || `${name} failed`);
    err.traceback = out.traceback;
    throw err;
  }
  return out.result;
}

// Yield to the browser so a progress line can paint before Python blocks it.
export const paint = () => new Promise((r) => setTimeout(r, 16));

export async function run(name, args = {}) {
  await paint();
  const started = performance.now();
  const result = call(name, args);
  return { result, ms: Math.round(performance.now() - started) };
}
