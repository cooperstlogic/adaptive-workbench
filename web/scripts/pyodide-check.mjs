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
//
// **The round goes to a laboratory on the way.** Approving submits and exports
// an order, and then stops; asking whether the results are back is a separate
// call, and the first ask is refused. Both asks are made here, because a
// harness that skipped the refusal would be testing a flow nobody runs.

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
const sent = call(py, "approve", { round_id: 4, by: BY });
timing.approve_ms = Date.now() - t;
report.submitted = {
  status: sent.status, expected: sent.expected, order: sent.order,
  n_samples: sent.n_samples, assay_version: sent.assay_version,
};
say(`approve round 4   submitted, ${sent.status}, expected ${(sent.expected || "?").slice(0, 10)}`
  + `, order ${sent.order}  ${timing.approve_ms} ms`);

t = Date.now();
const early = call(py, "check_results", { round_id: 4 });
timing.first_check_ms = Date.now() - t;
report.first_check = { ready: early.ready, status: early.status, expected: early.expected };
if (early.ready) throw new Error("the registry released round 4 on the first ask");
say(`check (1st)       not ready: ${early.status}, expected `
  + `${(early.expected || "?").slice(0, 10)} -- and the pull was refused`);

t = Date.now();
const approved = call(py, "check_results", { round_id: 4 });
timing.import_ms = Date.now() - t;
if (!approved.ready) throw new Error("the registry never released round 4");
report.round4 = {
  flagged: approved.flagged,
  mean_signed_residual: approved.anomaly.mean_signed_residual,
  z: approved.anomaly.z,
  bridge_offset: approved.frame.offset_estimate.offset,
  bridge_n: approved.frame.offset_estimate.n,
  authority: approved.frame.authority,
  rows: approved.reconciliation.rows,
  n_failed: approved.reconciliation.n_failed,
  n_censored: approved.reconciliation.n_censored,
};
say(`check (2nd)       ${approved.reconciliation.rows} rows, `
  + `${approved.reconciliation.n_failed} failed, `
  + `${approved.reconciliation.n_censored} censored; flagged=${approved.flagged}, `
  + `mean signed residual ${approved.anomaly.mean_signed_residual.toFixed(6)}, bridge `
  + `${approved.frame.offset_estimate.offset.toFixed(6)}  ${timing.import_ms} ms`);

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

// The other half of the redesign's Python: a project instantiated here, with
// its timestamp pinned, so check.py can compare it against one the CLI writes.
const CREATED = "2026-01-01T00:00:00+00:00";
t = Date.now();
const made = call(py, "create_project", {
  name: "harness-instantiated", lead: "trastuzumab", target: "HER2",
  team: "check.py", created: CREATED,
});
timing.create_ms = Date.now() - t;
report.created = {
  id: made.id, created: CREATED,
  n_designs: made.view.n_designs,
  batch_hash: made.view.rounds[0].batch.hash,
  mode: made.view.rounds[0].batch.mode,
};
say(`create            ${made.id}: round 1 ${made.view.rounds[0].batch.mode}, `
  + `${made.view.n_designs} designs, batch `
  + `${made.view.rounds[0].batch.hash.slice(7, 19)}  ${timing.create_ms} ms`);

// And the briefing, which has to be assembled from artifacts rather than
// narrated: every figure it returns names the core/ function behind it.
const brief = call(py, "ask", { key: "where_are_we" });
report.briefing = {
  kind: brief.kind, n_rounds: brief.n_rounds,
  best_observed: brief.best_observed && brief.best_observed.value,
  source: brief.best_observed && brief.best_observed.source,
  model_winner: brief.model_winner,
};
say(`briefing          ${brief.n_rounds} rounds, best observed `
  + `${(brief.best_observed || {}).value} pKD via ${(brief.best_observed || {}).source}`);

report.commands = after.log.map((e) => e.command);
timing.total_ms = Date.now() - t0;
if (json) {
  report.files = JSON.parse(py.runPython("wb_driver.json.dumps(wb_driver.dump_state())"));
  process.stdout.write(JSON.stringify(report));
} else {
  say(`\n${after.log.length} commands ran; total ${timing.total_ms} ms`);
}
