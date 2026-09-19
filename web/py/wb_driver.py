"""The browser's hands. It runs the pipeline; it computes nothing.

Every step below is the same script the CLI runs, invoked through the
``main(argv)`` entry point decision 71 put on each of them, in the same order
``run_rounds.py`` invokes them and with the same arguments. The difference is
the process: Pyodide has no ``subprocess``, so the calls are in-process and
stdout is captured rather than inherited. That is the whole of it. No
statistic, no threshold and no selection rule lives in this file, because a
second implementation of any of those is the fork CLAUDE.md's non-negotiable 2
forbids -- and the browser is the surface where it would be most tempting and
least visible.

What it does add is a **log**: every invocation, its argv, its exit code and
its output, appended to ``session/log.json``. The centre column renders that
log, so what an audience watches is a list of commands that actually ran
against the project on their own machine, not an animation of commands that
ran on ours.
"""

import contextlib
import importlib
import inspect
import io
import json
import os
import sys
import traceback

MOUNT = "/workbench"
SCRIPTS = os.path.join(MOUNT, "skills", "adaptive-optimization", "scripts")
for path in (SCRIPTS, MOUNT):
    if path not in sys.path:
        sys.path.insert(0, path)

import lims as lims_mod  # noqa: E402
from core import project, reconcile, schema  # noqa: E402

PROJECT = os.path.join(MOUNT, "projects", "demo-trastuzumab")
STORE = os.path.join(MOUNT, "lims_store", "demo-trastuzumab.json")
EXPORTS = os.path.join(MOUNT, "lims_store", "exports")
SESSION = os.path.join(MOUNT, "session")
LOG = os.path.join(SESSION, "log.json")
REFERENCE = os.path.join(MOUNT, "reference")

STEPS = ("generate_candidates", "select_batch", "import_round", "evaluate_prior",
         "fit_surrogates", "run_diagnostic", "record_decision")
_loaded = {}


def _script(name):
    if name not in _loaded:
        _loaded[name] = importlib.import_module(name)
    return _loaded[name]


# --- the log ---------------------------------------------------------------


def _log_read():
    if os.path.exists(LOG):
        with open(LOG, encoding="utf-8") as fh:
            return json.load(fh)
    return {"entries": []}


def _log_append(entry):
    os.makedirs(SESSION, exist_ok=True)
    log = _log_read()
    entry["n"] = len(log["entries"]) + 1
    log["entries"].append(entry)
    with open(LOG, "w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=1)
    return entry


def _shown(argv):
    """The command as the CLI would have been typed, repo-relative."""
    out = []
    for a in argv:
        a = str(a)
        if a.startswith(MOUNT + "/"):
            a = a[len(MOUNT) + 1:]
        out.append("'%s'" % a if " " in a else a)
    return " ".join(out)


def _call(kind, name, argv, label=None, note=None, round_id=None):
    """Run one pipeline step and record exactly what was run."""
    if any(a is None for a in argv):
        # str(None) is "None", which argparse accepts happily and which would
        # put a person called None into a record. An omitted argument is
        # omitted before it reaches here, never passed as a null.
        raise ValueError("%s was given a null argument: %r" % (name, argv))
    # Kept apart, because these scripts use the two streams for different
    # things: run_diagnostic prints a JSON record on stdout and its human
    # summary on stderr, and merging them makes the record unparseable.
    out, msg = io.StringIO(), io.StringIO()
    code, err = 0, None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(msg):
            if kind == "script":
                code = _script(name).main([str(a) for a in argv]) or 0
            else:
                code = lims_mod.main([str(a) for a in argv]) or 0
    except SystemExit as exc:                       # argparse and explicit exits
        code = int(exc.code or 0)
    except Exception:                               # noqa: BLE001 - shown to the user
        code, err = 1, traceback.format_exc(limit=3)
    entry = _log_append({
        "kind": kind,
        "tool": name,
        "round": None if round_id is None else int(round_id),
        "command": "python %s %s" % (
            "skills/adaptive-optimization/scripts/%s.py" % name if kind == "script"
            else "lims.py", _shown(argv)),
        "label": label or name.replace("_", " "),
        "note": note,
        "code": int(code),
        "output": out.getvalue().rstrip("\n"),
        "messages": (msg.getvalue() + (err or "")).rstrip("\n"),
    })
    if code:
        raise RuntimeError("%s exited %d\n%s"
                           % (name, code, entry["messages"] or entry["output"]))
    return entry


# --- reading the project ---------------------------------------------------


def _state():
    return project.load(PROJECT)


def _cumulative_best(state):
    """Best observed value the project held at the end of each round.

    Pooling is ``core.reconcile.pool`` -- the same function the fitting script
    and the selection script use -- applied to a prefix of the snapshots.
    """
    out = []
    for snap in project.snapshots(state):
        r = int(snap["round"])
        pooled = reconcile.pool(project.measurement_records(state, through=r))
        if not pooled:
            continue
        out.append({
            "round": r,
            "best_observed": max(v["value"] for v in pooled.values()),
            "n_measured": len(pooled),
            "flagged": bool(snap["flagged"]),
            "assay_version": snap["assay_version"],
            "offset_applied": float(snap["frame"]["offset_applied"]),
            "authority": snap["frame"]["authority"],
        })
    return out


def _round_view(state, entry):
    r = int(entry["round"])
    snap = project.read_artifact(state, "evidence", r)
    batch = project.read_artifact(state, "batches", r)
    ev = project.read_artifact(state, "batches", r, ".eval")
    run = project.read_artifact(state, "models", r)
    dec = project.read_decision(state, r)
    if snap is None:
        status = "awaiting approval" if batch else "not started"
    elif snap["flagged"] and not project.is_ruled(state, r):
        status = "flagged, ruling pending"
    elif snap["flagged"]:
        status = "flagged, ruled"
    else:
        status = "complete" if run else "imported"
    return {
        "round": r,
        "status": status,
        "flagged": None if snap is None else bool(snap["flagged"]),
        "ruled": project.is_ruled(state, r),
        "decision_status": None if dec is None else dec["status"],
        "decision_action": None if dec is None else dec["recommendation"]["action"],
        "verdict": None if not (dec and dec.get("ruling")) else dec["ruling"]["verdict"],
        "assay_version": None if snap is None else snap["assay_version"],
        "updated": entry.get("updated"),
        "refs": {k: entry[k] for k in ("pool", "batch", "snapshot", "evaluation",
                                       "model", "decision") if k in entry},
        "submission": entry.get("submission"),
        "batch": None if batch is None else {
            "hash": batch["hash"], "mode": batch["mode"], "n": len(batch["approved"]),
            "composition": batch["composition"], "approval": batch["approval"],
            "model_winner": batch["model_winner"], "incumbent": batch["incumbent"],
        },
        "anomaly": None if snap is None else snap["anomaly"],
        "frame": None if snap is None else snap["frame"],
        "calibration": None if ev is None else ev["calibration"],
        "improvement": None if ev is None else ev["improvement"],
        "model": None if run is None else {
            "hash": run["hash"], "winner": run["winner"],
            "n_observations": run["n_observations"],
            "recipes": {k: {kk: vv for kk, vv in v.items()
                            if kk in ("nlpd", "rmse", "coverage_80", "note")}
                        for k, v in run["recipes"].items()},
        },
    }


def view():
    """Everything the interface renders, assembled from artifacts on disk."""
    state = _state()
    entries = state["rounds"]["rounds"]
    rounds = [_round_view(state, e) for e in entries]
    pending = next((r for r in rounds if r["status"] == "awaiting approval"), None)
    blocked = next((r for r in rounds if r["status"] == "flagged, ruling pending"), None)
    last = rounds[-1] if rounds else None

    needs_you = None
    if blocked:
        dec = project.read_decision(state, blocked["round"])
        needs_you = {
            "kind": "ruling",
            "round": blocked["round"],
            "headline": "Round %d — ruling pending" % blocked["round"],
            "detail": ("%d hypotheses, %s recommended"
                       % (len(dec["hypotheses"]), dec["recommendation"]["action"])
                       if dec else "diagnosis not yet proposed"),
        }
    elif pending:
        needs_you = {
            "kind": "approval",
            "round": pending["round"],
            "headline": "Round %d — batch waiting for approval" % pending["round"],
            "detail": "%d wells, %s" % (pending["batch"]["n"], pending["batch"]["mode"]),
        }

    return {
        "project": state["project"],
        "objectives": state["objectives"],
        "n_designs": len(state["designs"]["designs"]),
        "rounds": rounds,
        "progress": _cumulative_best(state),
        "pending_round": None if pending is None else pending["round"],
        "blocked_round": None if blocked is None else blocked["round"],
        "active_round": (pending or blocked or last or {}).get("round"),
        "needs_you": needs_you,
        "log": _log_read()["entries"],
        "manifest": schema.read_json(os.path.join(MOUNT, "manifest.json")),
    }


def artifact(kind, round_id, suffix=""):
    """One artifact, whole, for the panel that renders it."""
    state = _state()
    if kind == "decision":
        rec = project.read_decision(state, int(round_id))
    else:
        rec = project.read_artifact(state, kind, int(round_id), suffix)
    return rec


def designs(ids):
    by_id = project.designs_by_id(_state())
    return [by_id[d] for d in ids if d in by_id]


# --- the loop --------------------------------------------------------------


def approve(round_id, by=None, drops=None, drop_notes=None):
    """Sign the batch, send it to the registry, pull what came back, import it.

    Re-running selection is not a formality. A batch with designs struck out
    is a different batch, and the record has to say who struck them and why,
    so the same script that chose them is the one that records the override.

    ``by`` is optional for one reason, and it is the reason the cross-surface
    claim is checkable: naming an approver stamps ``approval.at`` inside the
    hashed body, so every record downstream of a signature is unique to the
    run that signed it. Left unsigned, the whole chain is a pure function of
    its inputs and two surfaces produce identical bytes. The interface always
    names the person; the check never does.
    """
    r = int(round_id)
    argv = ["--project", PROJECT, "--round", r]
    if by:
        argv += ["--approved-by", by]
    for i, d in enumerate(drops or []):
        argv += ["--drop", d, "--drop-note", (drop_notes or [])[i] if
                 i < len(drop_notes or []) else ""]
    _call("script", "select_batch", argv, round_id=r,
          label=("approve batch %03d" % r) if by else ("re-select batch %03d" % r),
          note=("re-run with the approver named, so the record carries who signed it"
                if by else "no approver named, so the record carries no timestamp"))
    _call("lims", "submit", ["submit", "--project", PROJECT, "--round", r,
                             "--store", STORE],
          round_id=r, label="registry: submit_batch",
          note="the registry mints the construct and sample identifiers, not the workbench")
    os.makedirs(EXPORTS, exist_ok=True)
    csv_path = os.path.join(EXPORTS, "demo-trastuzumab_round%d.csv" % r)
    _call("lims", "pull", ["pull", "--project", PROJECT, "--round", "R%d" % r,
                           "--out", csv_path, "--store", STORE],
          round_id=r, label="registry: pull_assay_results",
          note="rows keyed by sample id -- no design id, no sequence, no ground truth")
    _call("script", "import_round",
          ["--project", PROJECT, "--round", r, "--results", csv_path,
           "--offset", "if-clear", "--authority",
           "bridge_policy:browser --offset if-clear"],
          round_id=r, label="import round %d" % r,
          note="a round that did not flag is normalized from its bridge; a flagged "
               "one is left raw for a human to rule on")
    _call("script", "evaluate_prior", ["--project", PROJECT, "--round", r],
          round_id=r, label="score round %d against its predictions" % r)
    state = _state()
    snap = project.read_artifact(state, "evidence", r)
    return {"round": r, "flagged": bool(snap["flagged"]),
            "anomaly": snap["anomaly"], "frame": snap["frame"]}


def diagnostic(round_id, test, by=None, offset=None, scope=None):
    """One read-only test from the library the template permits."""
    argv = ["--project", PROJECT, "--round", int(round_id), "--test", test]
    if by:
        argv += ["--by", by]
    if offset:
        argv += ["--offset", offset]
    if scope:
        argv += ["--scope", scope]
    entry = _call("script", "run_diagnostic", argv, round_id=int(round_id),
                  label="diagnostic: %s" % test, note="read-only; writes nothing")
    return {"test": test, "result": json.loads(entry["output"]), "log": entry}


def propose(round_id, payload):
    """Hand a proposal to the writer, which runs every test in it itself."""
    r = int(round_id)
    os.makedirs(SESSION, exist_ok=True)
    path = os.path.join(SESSION, "proposal_%03d.json" % r)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    _call("script", "record_decision",
          ["--project", PROJECT, "--round", r, "--propose", path],
          round_id=r, label="propose decision for round %d" % r,
          note="the payload names the tests; record_decision.py runs them and writes "
               "the numbers it got back")
    return artifact("decision", r)


def rule(round_id, verdict, by, note="", request=None):
    """The ruling. Four verbs, a named person, and nothing else moves data."""
    r = int(round_id)
    argv = ["--project", PROJECT, "--round", r, "--rule", verdict, "--by", by,
            "--note", note]
    if request:
        argv += ["--request", request]
    _call("script", "record_decision", argv, round_id=r,
          label="ruling: %s" % verdict,
          note="a named approver, recorded with the time; no action is taken on an "
               "unruled record")
    return artifact("decision", r)


def act_and_advance(round_id, next_round=True):
    """Do what the ruling authorized, then fit, then propose the next batch.

    The order and the arguments are SKILL.md step 9. ``import_round`` checks
    the authority itself: it will not move a frame under a ruling that
    recommended something else.
    """
    r = int(round_id)
    state = _state()
    dec = project.read_decision(state, r)
    if dec is None or dec["status"] != "ruled":
        raise RuntimeError("round %d has no ruling" % r)
    action = dec["recommendation"]["action"]
    verdict = dec["ruling"]["verdict"]
    authority = project.decision_id(r)
    csv_path = os.path.join(EXPORTS, "demo-trastuzumab_round%d.csv" % r)

    if verdict in ("accepted", "accepted_with_modification"):
        if action == "apply_offset_correction":
            _call("script", "import_round",
                  ["--project", PROJECT, "--round", r, "--results", csv_path,
                   "--offset", "always", "--authority", authority],
                  round_id=r, label="re-import round %d under %s" % (r, authority),
                  note="the correction runs in code, after the ruling, naming it")
            _call("script", "evaluate_prior", ["--project", PROJECT, "--round", r],
                  round_id=r, label="re-score round %d in the corrected frame" % r,
                  note="the evaluation records the snapshot hash it scored against, so "
                       "a moved frame needs a fresh one")
        elif action == "drop_wells":
            plates = dec["recommendation"]["parameters"].get("plates") or []
            argv = ["--project", PROJECT, "--round", r, "--results", csv_path,
                    "--authority", authority]
            for p in plates:
                argv += ["--drop-plate", p]
            _call("script", "import_round", argv,
                  label="re-import round %d, dropping %s" % (r, ", ".join(plates)))
            _call("script", "evaluate_prior", ["--project", PROJECT, "--round", r],
                  round_id=r, label="re-score round %d" % r)

    _call("script", "fit_surrogates", ["--project", PROJECT, "--round", r],
          round_id=r, label="fit round %d" % r,
          note="two recipes compete; the winner is the lowest held-out negative log "
               "predictive density")
    if next_round:
        advance(r + 1)
    return view()


def advance(round_id):
    """Enumerate, filter, and choose the next batch. Nobody has signed it yet."""
    r = int(round_id)
    _call("script", "generate_candidates", ["--project", PROJECT, "--round", r],
          round_id=r, label="enumerate and filter for round %d" % r,
          note="every declared constraint is enforced here, in code, before any model runs")
    _call("script", "select_batch", ["--project", PROJECT, "--round", r],
          round_id=r, label="select round %d" % r,
          note="no approver named, so the record is a pure function of its inputs and "
               "hashes the same on every surface")
    return artifact("batches", r)


def continue_unflagged(round_id):
    """A round that did not flag needs no ruling; fit it and move on."""
    r = int(round_id)
    _call("script", "fit_surrogates", ["--project", PROJECT, "--round", r],
          round_id=r, label="fit round %d" % r)
    advance(r + 1)
    return view()


# --- lineage ---------------------------------------------------------------


def lineage(dotted):
    """The function behind a number: where it lives, and what it says.

    This is the Notebook tab, and it is the whole of decision 107 rendered
    rather than argued. Every figure in a decision record names the `core/`
    function that produced it; this reads that function's source out of the
    same file Pyodide imported, so what is on screen is what ran.
    """
    module_name, _, qualname = dotted.rpartition(".")
    module = importlib.import_module(module_name)
    fn = getattr(module, qualname, None)
    if fn is None:
        return {"error": "no such function: %s" % dotted}
    rel = os.path.relpath(inspect.getsourcefile(fn), MOUNT)
    manifest = schema.read_json(os.path.join(MOUNT, "manifest.json"))
    sha = next((e["sha256"] for e in manifest["code"] if e["path"] == rel), None)
    source, lineno = inspect.getsourcelines(fn)
    return {
        "dotted": dotted, "file": rel, "sha256": sha, "first_line": lineno,
        "source": "".join(source).rstrip("\n"),
        "doc": inspect.getdoc(fn),
    }


def reference(name):
    path = os.path.join(REFERENCE, name)
    return schema.read_json(path) if os.path.exists(path) else None


# --- persistence -----------------------------------------------------------


def dump_state():
    """Every mutable file, so the page can put the visitor's progress away."""
    out = {}
    for root in (os.path.join(MOUNT, "projects"), os.path.join(MOUNT, "lims_store"),
                 SESSION):
        for base, _dirs, files in os.walk(root):
            for name in sorted(files):
                full = os.path.join(base, name)
                with open(full, encoding="utf-8") as fh:
                    out[os.path.relpath(full, MOUNT).replace(os.sep, "/")] = fh.read()
    return out


def call(name, payload="{}"):
    """One entry point, so the JavaScript side knows one calling convention."""
    args = json.loads(payload) if isinstance(payload, str) else dict(payload)
    fn = globals().get(name)
    if fn is None or name.startswith("_"):
        return json.dumps({"ok": False, "error": "no such call: %s" % name})
    try:
        return json.dumps({"ok": True, "result": fn(**args)}, default=str)
    except Exception as exc:                        # noqa: BLE001 - surfaced in the UI
        return json.dumps({"ok": False, "error": str(exc),
                           "traceback": traceback.format_exc(limit=4)})
