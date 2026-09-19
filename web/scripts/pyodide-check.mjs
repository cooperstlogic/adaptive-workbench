// Run the browser's Python path outside a browser, and hand the result to check.py.
//
//     node web/scripts/pyodide-check.mjs            # readable
//     node web/scripts/pyodide-check.mjs --json     # every artifact it wrote
//     node web/scripts/pyodide-check.mjs --by a.visitor
//
// The page claims to run the same science the terminal runs. The way to know
// is to boot the same Pyodide runtime the page boots, mount the same bundle,
// drive the same driver, and hand the files back for comparison against a CLI
// run of the same sequence. `check.py` does that comparison.
//
// Nothing here is a mock: the shipped runtime, the shipped wheel, the shipped
// bundle. The only thing missing is the window.
//
// **Unsigned by default.** Naming an approver stamps a timestamp inside the
// hashed body of the batch record, and every record downstream of it inherits
// that. Without a signature the whole chain is a pure function of its inputs,
// which is what makes byte-for-byte comparison of two surfaces meaningful.

import { readFile, readdir, stat } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WEB = dirname(HERE);
const PUBLIC = join(WEB, "public");
const BUNDLE = join(PUBLIC, "workbench");
const MOUNT = "/workbench";

const argv = process.argv.slice(2);
const json = argv.includes("--json");
const byArg = argv.indexOf("--by");
const BY = byArg >= 0 ? argv[byArg + 1] : null;
const say = (...a) => { if (!json) console.log(...a); };

async function walk(dir) {
  const out = [];
  for (const name of await readdir(dir)) {
    const full = join(dir, name);
    if ((await stat(full)).isDirectory()) out.push(...(await walk(full)));
    else out.push(full);
  }
  return out;
}

async function boot() {
  const { loadPyodide } = await import(pathToFileURL(join(PUBLIC, "pyodide", "pyodide.mjs")));
  const py = await loadPyodide({
    indexURL: join(PUBLIC, "pyodide") + "/", stdout: () => {}, stderr: () => {},
  });
  await py.loadPackage("numpy");
  const manifest = JSON.parse(await readFile(join(BUNDLE, "manifest.json"), "utf8"));
  py.FS.mkdirTree(MOUNT);
  for (const path of await walk(BUNDLE)) {
    const rel = relative(BUNDLE, path).split(/[\\/]/).join("/");
    const dest = `${MOUNT}/${rel}`;
    py.FS.mkdirTree(dest.slice(0, dest.lastIndexOf("/")));
    py.FS.writeFile(dest, new Uint8Array(await readFile(path)));
  }
  py.FS.mkdirTree(`${MOUNT}/session`);
  py.runPython(`import sys\nsys.path.insert(0, ${JSON.stringify(MOUNT)})\nimport wb_driver`);
  return { py, manifest };
}

const call = (py, name, args = {}) => {
  const raw = py.runPython(
    `wb_driver.call(${JSON.stringify(name)}, ${JSON.stringify(JSON.stringify(args))})`);
  const out = JSON.parse(raw);
  if (!out.ok) throw new Error(`${name}: ${out.error}\n${out.traceback || ""}`);
  return out.result;
};

const t0 = Date.now();
const { py, manifest } = await boot();
const timing = { boot_ms: Date.now() - t0 };
const report = { commit: manifest.commit, signed_by: BY, timing };
report.python = py.runPython("import sys; '%d.%d.%d' % sys.version_info[:3]");
report.numpy = py.runPython("import numpy; numpy.__version__");
say(`booted            pyodide, numpy ${report.numpy} on Python ${report.python}, `
  + `${manifest.code.length} modules  ${timing.boot_ms} ms`);

const opening = call(py, "view");
report.opening = {
  rounds: opening.rounds.length,
  pending_round: opening.pending_round,
  batch_hash: opening.rounds.at(-1).batch.hash,
  approval: opening.rounds.at(-1).batch.approval.status,
  designs: opening.n_designs,
};
say(`opening state     ${opening.rounds.length} rounds, round ${opening.pending_round} `
  + `${opening.rounds.at(-1).batch.approval.status}, batch `
  + `${report.opening.batch_hash.slice(7, 19)}`);

let t = Date.now();
const approved = call(py, "approve", { round_id: 4, by: BY });
timing.approve_ms = Date.now() - t;
report.round4 = {
  flagged: approved.flagged,
  mean_signed_residual: approved.anomaly.mean_signed_residual,
  z: approved.anomaly.z,
  bridge_offset: approved.frame.offset_estimate.offset,
  bridge_n: approved.frame.offset_estimate.n,
  authority: approved.frame.authority,
};
say(`approve round 4   flagged=${approved.flagged}, mean signed residual `
  + `${approved.anomaly.mean_signed_residual.toFixed(6)}, bridge `
  + `${approved.frame.offset_estimate.offset.toFixed(6)}  ${timing.approve_ms} ms`);

const proposal = JSON.parse(
  await readFile(join(BUNDLE, "reference", "decision_004.proposal.json"), "utf8"));
t = Date.now();
const record = call(py, "propose", {
  round_id: 4,
  payload: {
    trigger: proposal.trigger, hypotheses: proposal.hypotheses,
    recommendation: proposal.recommendation, ad_hoc: proposal.ad_hoc,
  },
});
timing.propose_ms = Date.now() - t;
report.decision = {
  status: record.status, action: record.recommendation.action,
  n_hypotheses: record.hypotheses.length,
  readings: record.hypotheses.map((h) => `${h.id}:${h.diagnostic}:${h.reading}`),
};
say(`propose round 4   ${record.hypotheses.length} hypotheses recomputed here, `
  + `recommends ${record.recommendation.action}  ${timing.propose_ms} ms`);

call(py, "rule", {
  round_id: 4, verdict: "accepted", by: BY || "check.py",
  note: "ruled by web/scripts/pyodide-check.mjs",
});

t = Date.now();
const after = call(py, "act_and_advance", { round_id: 4 });
timing.advance_ms = Date.now() - t;
const r4 = after.rounds.find((r) => r.round === 4);
const r5 = after.rounds.find((r) => r.round === 5);
report.after = {
  round4_authority: r4.frame.authority,
  round4_offset: r4.frame.offset_applied,
  round4_coverage: r4.calibration.realized_coverage,
  round4_model: r4.model.winner,
  round5_batch_hash: r5.batch.hash,
  round5_approval: r5.batch.approval.status,
};
say(`ruling accepted   round 4 frame ${r4.frame.offset_applied.toFixed(6)} under `
  + `${r4.frame.authority}, coverage ${r4.calibration.realized_coverage.toFixed(6)}`);
say(`advance           round 5 selected, batch ${r5.batch.hash.slice(7, 19)}, `
  + `model ${r4.model.winner}  ${timing.advance_ms} ms`);

report.commands = after.log.map((e) => e.command);
timing.total_ms = Date.now() - t0;
if (json) {
  report.files = JSON.parse(py.runPython("wb_driver.json.dumps(wb_driver.dump_state())"));
  process.stdout.write(JSON.stringify(report));
} else {
  say(`\n${after.log.length} commands ran; total ${timing.total_ms} ms`);
}
