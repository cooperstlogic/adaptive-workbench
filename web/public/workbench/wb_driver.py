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
its output, appended to ``session/<project>/log.json``. The centre column
renders that log, so what an audience watches is a list of commands that
actually ran against the project on their own machine, not an animation of
commands that ran on ours.

Three things the redesign added, and the rule each one obeys.

**A project is an argument.** Nothing here is bound to the demo any more:
every call takes a project id, resolves it under ``/workbench/projects``, and
the registry store beside it. ``create_project`` instantiates a new one by
calling ``init_project.py`` -- the CLI's own entry point, mirrored into the
bundle -- so a project born in a browser and a project born in a terminal are
the same four files.

**A round goes to a laboratory.** ``approve`` signs the batch, submits it and
writes the order file, and then stops. ``check_results`` is what asks whether
the assay has reported, and only a run that has reported gets imported.
Approving designs and reading their data used to be one click and about a
second, which is the least believable thing a person who has run an assay can
be shown.

**A briefing is assembled, never narrated.** ``ask`` answers a question about
the project by reading artifacts off disk and returning typed figures, each
carrying the ``core/`` function that produced it. There is no model in this
file and no sentence in it that a number could hide inside: the page renders
the figures, and the Notebook tab resolves every one of them to its source.

Phase 7 put a model in the centre seat, and this file is still where its
hands are. ``agent_context`` is what the model is handed -- artifacts, read
and flattened, never described. ``execute_analysis`` is the sixth question:
model-written numpy, run read-only against the mounted arrays behind a guard
that is labelled a guard. ``replay_plan`` and ``verify_diagnostic`` are the
other source for the same stream component: the committed record's claims,
each test re-run here and hash-compared against what the record holds. The
model itself lives behind ``web/function/ask.mjs`` and never touches
this filesystem; every tool call it makes lands in the log like everything
else, and the one thing it writes -- a proposal -- goes through ``propose``
and so through ``record_decision.py``, which recomputes every number in it.
"""

import contextlib
import hashlib
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
# Imported under a name of its own: every call below takes a ``project``
# argument, and a module shadowed by a parameter is a bug waiting for the
# one code path that does not pass it.
from core import project as project_mod  # noqa: E402
from core import amend, reconcile, schema  # noqa: E402

DEMO = "demo-trastuzumab"
PROJECTS_DIR = os.path.join(MOUNT, "projects")
STORE_DIR = os.path.join(MOUNT, "lims_store")
EXPORTS = os.path.join(STORE_DIR, "exports")
SESSIONS_DIR = os.path.join(MOUNT, "session")
REFERENCE = os.path.join(MOUNT, "reference")
TEMPLATES = os.path.join(MOUNT, "templates")

# How many projects this browser will instantiate. localStorage is about 5MB
# and a templated project with a round selected is a few hundred KB of JSON,
# so the ceiling is real rather than notional. It is here, in the driver,
# because a refusal a visitor can read beats a save that silently fails.
MAX_CREATED = 3

STEPS = ("generate_candidates", "select_batch", "import_round", "evaluate_prior",
         "fit_surrogates", "run_diagnostic", "record_decision", "amend_objectives")
_loaded = {}


def _script(name):
    if name not in _loaded:
        _loaded[name] = importlib.import_module(name)
    return _loaded[name]


def _root(project_id):
    return os.path.join(PROJECTS_DIR, project_id or DEMO)


def _store(project_id):
    return os.path.join(STORE_DIR, "%s.json" % (project_id or DEMO))


def _results_csv(project_id, round_id):
    return os.path.join(EXPORTS, "%s_round%d.csv" % (project_id or DEMO, int(round_id)))


def _order_csv(project_id, round_id):
    return os.path.join(EXPORTS, "%s_round%d_order.csv" % (project_id or DEMO, int(round_id)))


def _run_seed(project_id):
    """An independent replay of the same laboratory, per project.

    The landscape is pre-registered and never moves -- CLAUDE.md
    non-negotiable 8. What differs between two projects is the read noise:
    which constructs fail, where the run offset lands, which values censor.
    Derived from the name so it is reproducible, and pinned to 0 for the demo
    so the shipped campaign is the committed one.
    """
    if (project_id or DEMO) == DEMO:
        return 0
    return int(hashlib.sha256(project_id.encode("utf-8")).hexdigest()[:8], 16) % 100000


# --- the log ---------------------------------------------------------------


def _session_dir(project_id):
    return os.path.join(SESSIONS_DIR, project_id or DEMO)


def _log_path(project_id):
    return os.path.join(_session_dir(project_id), "log.json")


def _log_read(project_id):
    path = _log_path(project_id)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {"entries": []}


def _log_append(project_id, entry):
    os.makedirs(_session_dir(project_id), exist_ok=True)
    log = _log_read(project_id)
    entry["n"] = len(log["entries"]) + 1
    log["entries"].append(entry)
    with open(_log_path(project_id), "w", encoding="utf-8") as fh:
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


def _call(kind, name, argv, label=None, note=None, round_id=None, project=None,
          session=None, expect=None):
    """Run one pipeline step and record exactly what was run.

    ``expect`` names an exit code that is not a failure. Exactly one call in
    this file uses it: pulling a run the registry has not released. That
    refusal is the point of the two-moment flow rather than an accident in it,
    so it is run, shown, and not raised.
    """
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
            elif kind == "root":
                code = _script(name).main([str(a) for a in argv]) or 0
            else:
                code = lims_mod.main([str(a) for a in argv]) or 0
    except SystemExit as exc:                       # argparse and explicit exits
        code = int(exc.code or 0)
    except Exception:                               # noqa: BLE001 - shown to the user
        code, err = 1, traceback.format_exc(limit=3)
    shown = {"script": "skills/adaptive-optimization/scripts/%s.py" % name,
             "root": "%s.py" % name}.get(kind, "lims.py")
    entry = _log_append(project, {
        "kind": kind,
        "tool": name,
        "round": None if round_id is None else int(round_id),
        "session": session,
        "command": "python %s %s" % (shown, _shown(argv)),
        "label": label or name.replace("_", " "),
        "note": note,
        "code": int(code),
        "refused": bool(expect is not None and code == expect),
        "output": out.getvalue().rstrip("\n"),
        "messages": (msg.getvalue() + (err or "")).rstrip("\n"),
    })
    if code and code != expect:
        raise RuntimeError("%s exited %d\n%s"
                           % (name, code, entry["messages"] or entry["output"]))
    return entry


# --- reading the project ---------------------------------------------------


def _state(project_id=None):
    return project_mod.load(_root(project_id))


def _cumulative_best(state):
    """Best observed value the project held at the end of each round.

    Pooling is ``core.reconcile.pool`` -- the same function the fitting script
    and the selection script use -- applied to a prefix of the snapshots.
    """
    out = []
    for snap in project_mod.snapshots(state):
        r = int(snap["round"])
        pooled = reconcile.pool(project_mod.measurement_records(state, through=r))
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


def _lab_status(project_id, round_id, peek=True):
    """Where a round is with the laboratory, without moving it.

    ``peek`` reads the store directly rather than calling check_run_status,
    because asking is what releases a staggered round and rendering a rail is
    not asking. The one place that asks is ``check_results``.
    """
    path = _store(project_id)
    if not os.path.exists(path):
        return None
    store = schema.read_json(path)
    rec = store.get("rounds", {}).get("R%d" % int(round_id))
    if rec is None:
        return None
    return {"status": rec.get("status", "complete"),
            "assay_version": rec.get("assay_version"),
            "submitted": rec.get("submitted"),
            "expected": rec.get("expected"),
            "checks": int(rec.get("checks", 0)),
            "held": "release_on_check" in rec,
            "released_by": rec.get("released_by"),
            "released_at": rec.get("released_at"),
            "n_samples": rec.get("n_samples"),
            "n_rows": rec.get("n_rows")}


def _round_view(state, entry, project_id):
    r = int(entry["round"])
    snap = project_mod.read_artifact(state, "evidence", r)
    batch = project_mod.read_artifact(state, "batches", r)
    ev = project_mod.read_artifact(state, "batches", r, ".eval")
    run = project_mod.read_artifact(state, "models", r)
    dec = project_mod.read_decision(state, r)
    lab = _lab_status(project_id, r) if entry.get("submission") else None
    at_lab = bool(snap is None and lab and lab["status"] == "running")
    # The lab has reported and nobody has pulled it yet. Before the release
    # control existed this state lasted exactly as long as the call that
    # released the round, because the same ask imported it; now a person can
    # stand in it, and a round in it is not a round awaiting approval.
    reported = bool(snap is None and lab and lab["status"] != "running")
    if snap is None:
        if at_lab:
            status = "at the lab"
        elif reported:
            status = "results ready"
        elif batch:
            status = "awaiting approval"
        else:
            status = "not started"
    elif snap["flagged"] and not project_mod.is_ruled(state, r):
        status = "flagged, ruling pending"
    elif snap["flagged"]:
        status = "flagged, ruled"
    else:
        status = "complete" if run else "imported"
    return {
        "round": r,
        "status": status,
        "at_lab": at_lab,
        "reported": reported,
        "lab": lab,
        "flagged": None if snap is None else bool(snap["flagged"]),
        "ruled": project_mod.is_ruled(state, r),
        "decision_status": None if dec is None else dec["status"],
        "decision_action": None if dec is None else dec["recommendation"]["action"],
        "verdict": None if not (dec and dec.get("ruling")) else dec["ruling"]["verdict"],
        "assay_version": None if snap is None else snap["assay_version"],
        "updated": entry.get("updated"),
        "refs": {k: entry[k] for k in ("pool", "batch", "snapshot", "evaluation",
                                       "model", "decision") if k in entry},
        "submission": entry.get("submission"),
        # Only an order file that is actually on the mount, as the stream's
        # "submitted" step already does: a path the page cannot serve is a
        # download that fails on the click.
        "order": (_order_csv(project_id, r).replace(MOUNT + "/", "")
                  if entry.get("submission") and os.path.exists(_order_csv(project_id, r))
                  else None),
        "reconciliation": None if snap is None else snap["reconciliation"],
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


def view(project=None):
    """Everything the interface renders, assembled from artifacts on disk."""
    pid = project or DEMO
    state = _state(pid)
    entries = state["rounds"]["rounds"]
    rounds = [_round_view(state, e, pid) for e in entries]
    pending = next((r for r in rounds if r["status"] == "awaiting approval"), None)
    blocked = next((r for r in rounds if r["status"] == "flagged, ruling pending"), None)
    at_lab = next((r for r in rounds if r["at_lab"]), None)
    reported = next((r for r in rounds if r["reported"]), None)
    last = rounds[-1] if rounds else None

    needs_you = None
    if blocked:
        dec = project_mod.read_decision(state, blocked["round"])
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
    elif reported:
        needs_you = {
            "kind": "results",
            "round": reported["round"],
            "headline": "Round %d — the lab has reported" % reported["round"],
            "detail": "%d rows waiting to be pulled" % (reported["lab"]["n_rows"] or 0),
        }

    return {
        "project": state["project"],
        "objectives": state["objectives"],
        "n_designs": len(state["designs"]["designs"]),
        "rounds": rounds,
        "progress": _cumulative_best(state),
        "pending_round": None if pending is None else pending["round"],
        "blocked_round": None if blocked is None else blocked["round"],
        "at_lab_round": None if at_lab is None else at_lab["round"],
        "reported_round": None if reported is None else reported["round"],
        "active_round": (blocked or pending or reported or at_lab or last or {}).get("round"),
        "needs_you": needs_you,
        "log": _log_read(pid)["entries"],
        "sessions": sessions(pid),
        "manifest": schema.read_json(os.path.join(MOUNT, "manifest.json")),
    }


def artifact(kind, round_id, suffix="", project=None):
    """One artifact, whole, for the panel that renders it."""
    state = _state(project)
    if kind == "decision":
        return project_mod.read_decision(state, int(round_id))
    return project_mod.read_artifact(state, kind, int(round_id), suffix)


def designs(ids, project=None):
    by_id = project_mod.designs_by_id(_state(project))
    return [by_id[d] for d in ids if d in by_id]


# --- the projects on this machine ------------------------------------------


def projects():
    """Every project directory the browser holds, newest activity first."""
    out = []
    if not os.path.isdir(PROJECTS_DIR):
        return out
    for name in sorted(os.listdir(PROJECTS_DIR)):
        root = os.path.join(PROJECTS_DIR, name)
        if not os.path.isfile(os.path.join(root, "project.json")):
            continue
        state = project_mod.load(root)
        rounds = state["rounds"]["rounds"]
        snaps = project_mod.snapshots(state)
        best = None
        if snaps:
            pooled = reconcile.pool(project_mod.measurement_records(state))
            if pooled:
                best = max(v["value"] for v in pooled.values())
        flagged = sum(1 for s in snaps if s["flagged"])
        out.append({
            "id": name,
            "kind": "templated",
            "template": state["project"]["template"],
            "lead": state["project"]["lead"],
            "target": state["project"]["target"],
            "team": state["project"]["team"],
            "created": state["project"]["created"],
            "n_rounds": len(rounds),
            "n_designs": len(state["designs"]["designs"]),
            "n_flagged": flagged,
            "best_observed": best,
            "updated": rounds[-1].get("updated") if rounds else state["project"]["created"],
        })
    out.sort(key=lambda p: p["updated"] or "", reverse=True)
    return out


def templates():
    """The gallery's own contents, read from the template files themselves."""
    out = []
    if not os.path.isdir(TEMPLATES):
        return out
    for name in sorted(os.listdir(TEMPLATES)):
        path = os.path.join(TEMPLATES, name, "template.json")
        if os.path.isfile(path):
            out.append(schema.read_json(path))
    return out


def create_project(name, template="antibody-affinity-maturation", lead=None, target="HER2",
                   team="", created=None):
    """Instantiate a project and select its first batch, through the CLI's own path.

    Three commands, in the order a person would type them. The first is
    ``init_project.py`` -- not one of the skill's seven scripts, because the
    skill operates on a project that already exists -- and the next two are
    round 1 going through enumeration and selection like every other round.
    Nothing here writes a design or a batch directly; a round-1 batch written
    by a second code path is a batch with no record, no rationale and no
    approval.
    """
    name = str(name or "").strip()
    if not name:
        raise ValueError("a project needs a name")
    if not all(c.isalnum() or c in "-_" for c in name):
        raise ValueError("project names are letters, digits, hyphens and underscores: %r"
                         % name)
    if os.path.exists(os.path.join(_root(name), "project.json")):
        raise ValueError("a project called %r already exists in this browser" % name)
    created_here = [p for p in projects() if p["id"] != DEMO]
    if len(created_here) >= MAX_CREATED:
        raise ValueError(
            "this browser holds %d created projects already, which is the cap. Everything "
            "here lives in localStorage, and localStorage is about 5MB -- a templated "
            "project with a round selected is a few hundred KB of it. Reset, or delete one."
            % len(created_here))

    argv = ["--template", template, "--name", name, "--target", target,
            "--projects-dir", PROJECTS_DIR]
    if lead:
        argv += ["--lead", lead]
    if team:
        argv += ["--team", team]
    if created:
        argv += ["--created", created]
    _call("root", "init_project", argv, project=name,
          label="instantiate %s from %s" % (name, template),
          note="the template declares the objectives, the constraints, the recipes, the "
               "diagnostics and the batch policy; three facts come from the person")
    root = _root(name)
    _call("script", "generate_candidates", ["--project", root, "--round", 1],
          round_id=1, project=name, label="enumerate and filter for round 1",
          note="every declared constraint is enforced here, in code, before any model runs")
    _call("script", "select_batch", ["--project", root, "--round", 1],
          round_id=1, project=name, label="select round 1",
          note="round 1 is the template's declared policy -- a single-mutant scan -- not "
               "a model's opinion, because there is nothing fitted yet")
    return {"id": name, "view": view(name)}


def delete_project(project):
    """Remove a project this browser created. The demo is not removable."""
    import shutil                                        # noqa: PLC0415
    pid = str(project or "")
    if pid == DEMO:
        raise ValueError("the shipped campaign is not deletable; Reset restores it")
    root = _root(pid)
    if not os.path.isdir(root):
        raise ValueError("no such project: %r" % pid)
    shutil.rmtree(root)
    for path in (_store(pid), _session_dir(pid)):
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.exists(path):
            os.remove(path)
    return {"deleted": pid}


# --- the loop --------------------------------------------------------------


def _override_args(batch):
    """The `--set` flags that reproduce a batch record's policy overrides."""
    moved = (batch or {}).get("policy_overrides") or []
    if not moved:
        return []
    argv = []
    for rec in moved:
        argv += ["--set", "%s=%s" % (rec["field"], rec["to"])]
    argv += ["--set-note", moved[0].get("note") or ""]
    if moved[0].get("by"):
        argv += ["--set-by", moved[0]["by"]]
    return argv


def revise_batch(round_id, changes, why="", by=None, project=None, session=None):
    """Re-compose an unapproved batch under a changed policy.

    The other half of the override story, and the everyday half. An amendment
    says the declaration is wrong from here on, needs evidence behind it and a
    named person to rule on it. This says *this* batch should have been put
    together differently -- more wells on uncertainty, a wider bridge -- and
    it needs none of that, because nothing has gone anywhere. What gates it is
    the approval that gates every batch and has not happened yet.

    ``changes`` is a list of {"field", "to"}. The bounds are the same ones an
    amendment is held to, checked in ``core.amend`` before selection re-runs,
    and ``select_batch.py`` refuses a round the laboratory already has.
    """
    r = int(round_id)
    pid = project or DEMO
    moved = [(c["field"], c["to"]) for c in (changes or [])]
    if not moved:
        raise RuntimeError("name at least one policy field to change")
    argv = ["--project", _root(pid), "--round", r]
    for field, to in moved:
        argv += ["--set", "%s=%s" % (field, to)]
    argv += ["--set-note", why or ""]
    if by:
        argv += ["--set-by", by]
    entry = _call("script", "select_batch", argv, round_id=r, project=pid, session=session,
                  label="re-select batch %03d: %s" % (r, ", ".join("%s=%s" % m for m in moved)),
                  note="the same bounds an amendment is held to, checked before selection "
                       "re-runs; objectives.json is untouched and the next round reverts "
                       "to it")
    record = artifact("batches", r, project=pid)
    return {"round": r, "composition": record["composition"],
            "policy_overrides": record.get("policy_overrides") or [],
            "hash": record["hash"], "log": entry}


def approve(round_id, by=None, drops=None, drop_notes=None, project=None, stagger=True,
            session=None):
    """Sign the batch, send it to the registry, and write the order for the lab.

    Where this used to end -- pulled back, reconciled, scored, in the same
    second -- it now stops. The round is at the laboratory and nothing about
    it is knowable until the assay reports. ``check_results`` is the other
    half.

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
    pid = project or DEMO
    root, store = _root(pid), _store(pid)
    argv = ["--project", root, "--round", r]
    if by:
        argv += ["--approved-by", by]
    for i, d in enumerate(drops or []):
        argv += ["--drop", d, "--drop-note", (drop_notes or [])[i] if
                 i < len(drop_notes or []) else ""]
    # Approving re-runs selection so the record carries who signed it, which
    # means any policy override the batch was re-composed under has to be
    # passed again or signing it would quietly put it back. The batch record
    # is where they live, so it is where they are read from.
    argv += _override_args(project_mod.read_artifact(_state(pid), "batches", r))
    _call("script", "select_batch", argv, round_id=r, project=pid, session=session,
          label=("approve batch %03d" % r) if by else ("re-select batch %03d" % r),
          note=("re-run with the approver named, so the record carries who signed it"
                if by else "no approver named, so the record carries no timestamp"))
    submit = ["submit", "--project", root, "--round", r, "--store", store,
              "--run-seed", _run_seed(pid)]
    if stagger:
        submit += ["--stagger"]
    _call("lims", "submit", submit, round_id=r, project=pid, session=session,
          label="registry: submit_batch",
          note="the registry mints the construct and sample identifiers, not the "
               "workbench, and it holds the round open until the assay reports")
    os.makedirs(EXPORTS, exist_ok=True)
    order = _order_csv(pid, r)
    _call("lims", "export", ["export", "--project", root, "--round", "R%d" % r,
                             "--out", order, "--store", store],
          round_id=r, project=pid, session=session, label="registry: export_submission",
          note="the order the lab receives: construct, sample, design, plate, sequence. "
               "No value column, because an order is not a result")
    lab = _lab_status(pid, r) or {}
    return {"round": r, "status": lab.get("status", "complete"),
            "expected": lab.get("expected"), "submitted": lab.get("submitted"),
            "assay_version": lab.get("assay_version"), "n_samples": lab.get("n_samples"),
            "order": order.replace(MOUNT + "/", "")}


def check_results(round_id, project=None, session=None):
    """Ask the registry whether the round has reported, and import it if it has.

    Asking is the only thing that moves a staggered round, which is why this
    is the one call that asks. A run that has not reported comes back with the
    date it is expected -- and with the registry refusing the pull, run and
    shown rather than described, because that refusal is the substance of the
    boundary and not a caption on it.

    When it has reported, the import and the scoring run as the continuation
    of the same answer: the arrival is the first moment there is anything to
    say, and what there is to say is the reconciliation and the anomaly
    verdict together.
    """
    r = int(round_id)
    pid = project or DEMO
    root, store = _root(pid), _store(pid)
    state = _state(pid)
    entry = next((e for e in state["rounds"]["rounds"] if int(e["round"]) == r), None)
    if entry is None or not entry.get("submission"):
        raise RuntimeError("round %d has not been submitted; there is nothing at the "
                           "laboratory to ask about" % r)
    if project_mod.read_artifact(state, "evidence", r) is not None:
        # The registry would hand the rows over again -- pulling is a read --
        # but importing them again would rewrite a snapshot that has already
        # been scored, ruled on and in round 4's case moved into a corrected
        # frame. A round comes back once.
        raise RuntimeError("round %d is already imported; evidence/snapshot_%03d.json "
                           "holds what came back" % (r, r))
    ran = []
    entry = _call("lims", "status", ["status", "--project", root, "--round", "R%d" % r,
                                     "--store", store],
                  round_id=r, project=pid, session=session,
                  label="registry: check_run_status",
                  note="binary: a run either has results to hand over or it does not")
    ran.append(entry)
    lab = _lab_status(pid, r) or {}
    if lab.get("status") == "running":
        ran.append(_call("lims", "pull", ["pull", "--project", root, "--round", "R%d" % r,
                                          "--out", _results_csv(pid, r), "--store", store],
                         round_id=r, project=pid, session=session, expect=2,
                         label="registry: pull_assay_results — refused",
                         note="asked anyway, so the refusal is shown rather than described"))
        return {"round": r, "ready": False, "status": "running",
                "expected": lab.get("expected"), "submitted": lab.get("submitted"),
                "assay_version": lab.get("assay_version"),
                "refusal": entry["output"], "ran": ran}

    csv_path = _results_csv(pid, r)
    ran.append(_call("lims", "pull", ["pull", "--project", root, "--round", "R%d" % r,
                                      "--out", csv_path, "--store", store],
                     round_id=r, project=pid, session=session,
                     label="registry: pull_assay_results",
                     note="rows keyed by sample id -- no design id, no sequence, no "
                          "ground truth"))
    ran.append(_call("script", "import_round",
                     ["--project", root, "--round", r, "--results", csv_path,
                      "--offset", "if-clear", "--authority",
                      "bridge_policy:browser --offset if-clear"],
                     round_id=r, project=pid, session=session,
                     label="import round %d" % r,
                     note="a round that did not flag is normalized from its bridge; a "
                          "flagged one is left raw for a human to rule on"))
    ran.append(_call("script", "evaluate_prior", ["--project", root, "--round", r],
                     round_id=r, project=pid, session=session,
                     label="score round %d against its predictions" % r))
    snap = project_mod.read_artifact(_state(pid), "evidence", r)
    return {"round": r, "ready": True, "status": "complete", "ran": ran,
            "flagged": bool(snap["flagged"]), "anomaly": snap["anomaly"],
            "frame": snap["frame"], "reconciliation": snap["reconciliation"],
            "assay_version": snap["assay_version"], "source": snap["source"],
            "plates": sorted({p for m in snap["measurements"]
                               for p in (m.get("plates") or [])})}


def release_run(round_id, project=None, session=None, reason=None):
    """Simulated: tell the laboratory to report a round it is still running.

    Every other control in this file is a real call to a real script. This
    one moves the clock, and it exists because the clock is the only thing in
    the demo that cannot be waited on honestly: the assay takes eight days,
    the page says so, and a visitor with ten minutes has no way through that
    sentence. ``check_run_status`` already releases a held round on the ask
    after the first, which is a rule nobody watching can see; this is the
    same release with a control on it that says what it is.

    It is labelled everywhere it appears -- *simulated* on the button, the
    reason in the registry's record, the command in the log like every other
    command. What it does not touch is the data: the values were measured by
    the oracle at submission, and releasing changes when the registry hands
    them over and nothing about what they say. Nothing is imported here
    either; the round is still pulled by the ask that asks for it.
    """
    r = int(round_id)
    pid = project or DEMO
    lab = _lab_status(pid, r)
    if lab is None:
        raise RuntimeError("round %d has not been submitted to the registry" % r)
    if lab["status"] != "running":
        raise RuntimeError("round %d is not being held: the registry has it as %s"
                           % (r, lab["status"]))
    _call("lims", "release",
          ["release", "--project", _root(pid), "--round", "R%d" % r,
           # No apostrophe: the log renders a command as it would have been
           # typed, and an argument that needs quoting must survive it.
           "--store", _store(pid), "--reason", reason or "the demo control"],
          round_id=r, project=pid, session=session,
          label="simulated: the assay reports",
          note="a demo device and the only one in this file: it moves the laboratory's "
               "clock, never its data. The values were measured at submission")
    return {"round": r, "lab": _lab_status(pid, r)}


def diagnostic(round_id, test, by=None, offset=None, scope=None, project=None,
               session=None, verify=None):
    """One read-only test from the library the template permits.

    ``verify`` names a pass and a hypothesis in the committed record; when
    given, the result is hash-compared against what that record holds, on
    this side of the JSON boundary so that ``0.0`` is still a float. The page
    renders the number computed here and says whether it matched.
    """
    pid = project or DEMO
    argv = ["--project", _root(pid), "--round", int(round_id), "--test", test]
    if by:
        argv += ["--by", by]
    if offset:
        argv += ["--offset", offset]
    if scope:
        argv += ["--scope", scope]
    entry = _call("script", "run_diagnostic", argv, round_id=int(round_id), project=pid,
                  session=session, label="diagnostic: %s" % test,
                  note="read-only; writes nothing")
    record = json.loads(entry["output"])
    out = {"test": test, "result": record, "log": entry}
    if verify:
        out["verified"] = _verify_diagnostic(int(round_id), verify.get("pass", 1),
                                             verify.get("hypothesis"), record["result"], pid)
    return out


def propose(round_id, payload, project=None, session=None):
    """Hand a proposal to the writer, which runs every test in it itself.

    The payload is the same whether a live model wrote it, the recorded one
    is being stepped, or a person typed it: claims, the test each rests on,
    a reading, and a recommendation. ``record_decision.py`` refuses a payload
    carrying its own ``result``, so this is the one door into ``decisions/``
    and no number walks through it.
    """
    r = int(round_id)
    pid = project or DEMO
    os.makedirs(_session_dir(pid), exist_ok=True)
    existing = project_mod.read_decision(_state(pid), r)
    n_pass = (existing or {}).get("n_passes", 0) + 1
    path = os.path.join(_session_dir(pid), "proposal_%03d_pass%d.json" % (r, n_pass))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    _call("script", "record_decision",
          ["--project", _root(pid), "--round", r, "--propose", path],
          round_id=r, project=pid, session=session,
          label="propose decision for round %d%s" % (r, "" if n_pass == 1
                                                     else ", pass %d" % n_pass),
          note="the payload names the tests; record_decision.py runs them and writes "
               "the numbers it got back")
    return artifact("decision", r, project=pid)


def rule(round_id, verdict, by, note="", request=None, amend_to=None, project=None,
         session=None):
    """The ruling. Four verbs, a named person, and nothing else moves data.

    ``amend_to`` is the one number a ruling carries, and it belongs to
    ``accepted_with_modification``: a recommendation that proposes an
    amendment proposes a value, and the person ruling on it dials that value
    rather than only taking or leaving it. The writer re-validates it against
    the same declared bounds the proposal was checked against.
    """
    r = int(round_id)
    pid = project or DEMO
    argv = ["--project", _root(pid), "--round", r, "--rule", verdict, "--by", by,
            "--note", note]
    if request:
        argv += ["--request", request]
    if amend_to is not None:
        argv += ["--amend-to", str(amend_to)]
    _call("script", "record_decision", argv, round_id=r, project=pid, session=session,
          label="ruling: %s" % verdict,
          note="a named approver, recorded with the time; no action is taken on an "
               "unruled record")
    return artifact("decision", r, project=pid)


def act_and_advance(round_id, next_round=True, project=None, session=None):
    """Do what the ruling authorized, then fit, then propose the next batch.

    The order and the arguments are SKILL.md step 9. ``import_round`` checks
    the authority itself: it will not move a frame under a ruling that
    recommended something else.
    """
    r = int(round_id)
    pid = project or DEMO
    root = _root(pid)
    state = _state(pid)
    dec = project_mod.read_decision(state, r)
    if dec is None or dec["status"] != "ruled":
        raise RuntimeError("round %d has no ruling" % r)
    action = dec["recommendation"]["action"]
    verdict = dec["ruling"]["verdict"]
    authority = project_mod.decision_id(r)
    csv_path = _results_csv(pid, r)

    if verdict in ("accepted", "accepted_with_modification"):
        if action == "apply_offset_correction":
            _call("script", "import_round",
                  ["--project", root, "--round", r, "--results", csv_path,
                   "--offset", "always", "--authority", authority],
                  round_id=r, project=pid, session=session,
                  label="re-import round %d under %s" % (r, authority),
                  note="the correction runs in code, after the ruling, naming it")
            _call("script", "evaluate_prior", ["--project", root, "--round", r],
                  round_id=r, project=pid, session=session,
                  label="re-score round %d in the corrected frame" % r,
                  note="the evaluation records the snapshot hash it scored against, so "
                       "a moved frame needs a fresh one")
        elif action == "drop_wells":
            plates = dec["recommendation"]["parameters"].get("plates") or []
            argv = ["--project", root, "--round", r, "--results", csv_path,
                    "--authority", authority]
            for p in plates:
                argv += ["--drop-plate", p]
            _call("script", "import_round", argv, round_id=r, project=pid, session=session,
                  label="re-import round %d, dropping %s" % (r, ", ".join(plates)))
            _call("script", "evaluate_prior", ["--project", root, "--round", r],
                  round_id=r, project=pid, session=session, label="re-score round %d" % r)

    # An amendment is the other half of a ruling: the action says what happens
    # to this round's data, the amendment says how the next round's wells are
    # spent or what they may be spent on. They are independent, so a record
    # can carry both and this runs both.
    amendment = (dec["recommendation"] or {}).get("amendment")
    if amendment:
        _call("script", "amend_objectives", ["--project", root, "--authority", authority],
              round_id=r, project=pid, session=session,
              label="amend %s under %s" % (amendment["field"], authority),
              note="the bounds are declared in core/amend.py and checked before the write; "
                   "the superseded value stays in the amendments block")
        state = _state(pid)
        moved = bool((state["objectives"].get("amendments") or [])[-1]["effects"]
                     ["pool_changes"])
    else:
        moved = False

    if not moved:
        _call("script", "fit_surrogates", ["--project", root, "--round", r],
              round_id=r, project=pid, session=session, label="fit round %d" % r,
              note="two recipes compete; the winner is the lowest held-out negative log "
                   "predictive density")
        if next_round:
            advance(r + 1, project=pid, session=session)
        return view(pid)

    # The window moved, so the pool moved, and a model run holds one
    # prediction per pool member in pool order. The next round's pool has to
    # exist before this round can be fitted against it, which inverts the two
    # steps `advance` does in the ordinary case -- so the three commands are
    # spelled out here rather than reached through it.
    if not next_round:
        return view(pid)
    _call("script", "generate_candidates", ["--project", root, "--round", r + 1],
          round_id=r + 1, project=pid, session=session,
          label="re-enumerate for round %d under the amended window" % (r + 1),
          note="every declared constraint is enforced here, in code, before any model runs")
    _call("script", "fit_surrogates", ["--project", root, "--round", r,
                                       "--pool", r + 1],
          round_id=r, project=pid, session=session,
          label="fit round %d over the amended pool" % r,
          note="the amended pool is what the next batch is chosen from, so it is the pool "
               "this run has to predict over")
    _call("script", "select_batch", ["--project", root, "--round", r + 1],
          round_id=r + 1, project=pid, session=session, label="select round %d" % (r + 1),
          note="no approver named, so the record is a pure function of its inputs and "
               "hashes the same on every surface")
    return view(pid)


def advance(round_id, project=None, session=None):
    """Enumerate, filter, and choose the next batch. Nobody has signed it yet."""
    r = int(round_id)
    pid = project or DEMO
    root = _root(pid)
    _call("script", "generate_candidates", ["--project", root, "--round", r],
          round_id=r, project=pid, session=session,
          label="enumerate and filter for round %d" % r,
          note="every declared constraint is enforced here, in code, before any model runs")
    _call("script", "select_batch", ["--project", root, "--round", r],
          round_id=r, project=pid, session=session, label="select round %d" % r,
          note="no approver named, so the record is a pure function of its inputs and "
               "hashes the same on every surface")
    return artifact("batches", r, project=pid)


def continue_unflagged(round_id, project=None, session=None):
    """A round that did not flag needs no ruling; fit it and move on."""
    r = int(round_id)
    pid = project or DEMO
    _call("script", "fit_surrogates", ["--project", _root(pid), "--round", r],
          round_id=r, project=pid, session=session, label="fit round %d" % r)
    advance(r + 1, project=pid, session=session)
    return view(pid)


# --- sessions --------------------------------------------------------------
#
# A session is a unit of work inside a project. A new round starts one, and a
# person can start an ad-hoc one at any time. Round sessions are derived from
# the round graph and are not stored; ad-hoc ones are, beside the log, so a
# reload keeps them.


def _is_round(session_id):
    """A round session is named for its round; an ad-hoc one is not."""
    sid = str(session_id or "")
    return len(sid) > 1 and sid[0] == "r" and sid[1:].isdigit()


def _adhoc_path(project_id):
    return os.path.join(_session_dir(project_id), "sessions.json")


def _adhoc_read(project_id):
    path = _adhoc_path(project_id)
    if os.path.exists(path):
        return schema.read_json(path)
    return {"sessions": []}


def _adhoc_write(project_id, doc):
    os.makedirs(_session_dir(project_id), exist_ok=True)
    schema.write_json(_adhoc_path(project_id), doc)


def sessions(project=None):
    """Both kinds, interleaved by recency, the way the rail lists them."""
    pid = project or DEMO
    out = []
    if os.path.isfile(os.path.join(_root(pid), "project.json")):
        state = _state(pid)
        for entry in state["rounds"]["rounds"]:
            r = int(entry["round"])
            rv = _round_view(state, entry, pid)
            out.append({
                "id": "r%d" % r, "kind": "round", "round": r,
                "title": "Round %d" % r, "subtitle": rv["status"],
                "flagged": bool(rv["flagged"]), "at_lab": rv["at_lab"],
                "reported": rv["reported"],
                "needs_you": rv["status"] in ("awaiting approval", "flagged, ruling pending",
                                              "results ready"),
                "updated": entry.get("updated"),
            })
    for s in _adhoc_read(pid)["sessions"]:
        if _is_round(s["id"]):
            continue
        out.append({
            "id": s["id"], "kind": "adhoc", "round": None, "reported": False,
            "title": s.get("title") or "New session",
            "subtitle": "%d %s" % (len(s.get("turns", [])),
                                   "exchange" if len(s.get("turns", [])) == 1
                                   else "exchanges"),
            "flagged": False, "at_lab": False, "needs_you": False,
            "updated": s.get("updated") or s.get("created"),
        })
    out.sort(key=lambda s: s["updated"] or "", reverse=True)
    return out


def session(session_id, project=None):
    """One ad-hoc session, with everything that was asked in it."""
    pid = project or DEMO
    for s in _adhoc_read(pid)["sessions"]:
        if s["id"] == session_id:
            return s
    return None


def new_session(project=None, created=None):
    """An empty ad-hoc session. It holds no state until something is asked in it.

    An empty one is reused rather than added to. Clicking New twice is one
    intention, not two, and a rail filling with blank sessions nobody opened
    is the kind of small dishonesty that makes a demo look unfinished.
    """
    pid = project or DEMO
    doc = _adhoc_read(pid)
    spare = next((s for s in doc["sessions"]
                  if not _is_round(s["id"]) and not s["turns"]), None)
    if spare is not None:
        return spare
    n = len(doc["sessions"]) + 1
    rec = {"id": "s%03d" % n, "kind": "adhoc", "title": None,
           "created": created or "", "updated": created or "", "turns": []}
    doc["sessions"].append(rec)
    _adhoc_write(pid, doc)
    return rec


def ask(key, project=None, session_id=None, round_id=None, at=None):
    """Answer a question about the project by reading its artifacts.

    There is no model here and no prose assembled around a number. What comes
    back is a typed briefing: named figures, each carrying the ``core/``
    function that produced it and the artifact it was read out of, which the
    Notebook tab resolves. Phase 7 puts a live model in this seat and free
    text starts working; until then the suggested asks are the vocabulary, and
    they are answered from state rather than from a transcript.
    """
    pid = project or DEMO
    # One ask is not a read of state but a question put to the registry, and
    # asking is what moves a staggered round. It goes through the same call the
    # rest of the loop uses, so what happens is in the log with everything
    # else -- and it is an ask rather than a button because it is a question.
    if key == "results_back" and round_id is not None:
        answer = _lab_briefing(pid, int(round_id), session_id)
    else:
        answer = _briefing(pid, key, round_id)
    if session_id:
        doc = _adhoc_read(pid)
        rec = next((s for s in doc["sessions"] if s["id"] == session_id), None)
        if rec is None:
            # A round session has no stored record until something is asked in
            # it; its identity comes from the round graph. This creates the
            # place to put the turn without inventing a session.
            rec = {"id": session_id, "kind": "round" if _is_round(session_id) else "adhoc",
                   "title": None, "created": at or "", "updated": at or "", "turns": []}
            doc["sessions"].append(rec)
        rec["turns"].append({"key": key, "round": round_id, "at": at or "",
                             "after_n": len(_log_read(pid)["entries"]),
                             "question": answer["question"], "answer": answer})
        rec["updated"] = at or rec.get("updated") or ""
        if not rec.get("title") and not _is_round(session_id):
            rec["title"] = answer["question"]
        _adhoc_write(pid, doc)
    return answer


def _lab_briefing(pid, round_id, session_id):
    """Ask the laboratory, and say what came back.

    Not ready is an answer: it names the date and leaves the ask offered. Ready
    is where there is finally something to say, and the reconciliation and the
    anomaly verdict land in the same turn, because the arrival is one event.

    A seed round has no verdict to land: nothing predicted it, so there is no
    residual to take and ``anomaly_flag`` returned none. ``scored`` says which
    kind of arrival this is, and the figures are absent rather than zero.
    """
    res = check_results(round_id, project=pid, session=session_id)
    res.pop("ran", None)
    base = {"key": "results_back", "question": QUESTIONS["results_back"] % round_id,
            "project": pid, "round": round_id, "kind": "arrival",
            "reads": ["lims_store/%s.json" % pid]}
    if not res["ready"]:
        return dict(base, ready=False, status=res["status"],
                    submitted=res.get("submitted"), expected=res.get("expected"),
                    assay_version=res.get("assay_version"), refusal=res.get("refusal"))
    rec = res["reconciliation"]
    out = dict(base, ready=True, status="complete",
               assay_version=res["assay_version"], plates=res["plates"],
               rows=rec["rows"], samples=rec["samples"], designs=rec["designs"],
               n_ok=rec["n_ok"], n_failed=rec["n_failed"], n_censored=rec["n_censored"],
               unreconciled=rec["unreconciled_rows"],
               flagged=res["flagged"], scored=res["anomaly"] is not None,
               reads=["lims_store/%s.json" % pid,
                      "evidence/snapshot_%03d.json" % round_id])
    if res["anomaly"] is None:
        # A round chosen without a model -- the seed round of any project --
        # was predicted by nothing, so there is no residual to take and
        # `anomaly_flag` returned none. It came back and it is in; the
        # sentence about where the model put these designs has no subject.
        return out
    return dict(out,
                statistic=_figure(res["anomaly"]["mean_signed_residual"],
                                  "core.reconcile.anomaly_flag",
                                  "evidence/snapshot_%03d.json" % round_id,
                                  "mean signed residual", "pKD"),
                trigger=_figure(res["anomaly"]["trigger_abs_pkd"],
                                "core.reconcile.anomaly_flag", "objectives.json",
                                "trigger", "pKD"),
                n_compared=res["anomaly"]["n_compared"],
                known_version_offset=res["anomaly"]["known_version_offset"])


def _figure(value, source, artifact_path, label, unit=None, synthetic=False, args=None):
    """A number on screen, with the function that produced it attached.

    Every figure in a briefing goes through here, so none of them can be a
    number this file computed. ``source`` is the ``core/`` function; the
    Notebook tab reads its source out of the same file Pyodide imported.
    """
    return {"value": value, "unit": unit, "label": label, "source": source,
            "artifact": artifact_path, "synthetic": bool(synthetic),
            "args": args or {}}


def round_history(round_id, project=None):
    """What happened in a round, read back out of the artifacts it wrote.

    A round that ran before this browser was opened has no command log here
    -- the log is this tab's, and the shipped campaign's first three rounds
    ran on a laptop six weeks ago -- so their sessions were a title and a
    composer and nothing else. That is a lie about the project by omission:
    those rounds were proposed, signed for, ordered, returned and scored, and
    every one of those moments is on disk in a file with a hash.

    So this reads them back. It is the briefing pattern applied to one round:
    typed steps, each carrying the artifact it was read from and the ``core/``
    function behind any number in it, assembled and never narrated. What it
    is not is a transcript. No command chip is rendered from it, because no
    command ran in this tab; the page says *read from the record* and names
    the files. A round whose steps did happen here has its own log and gets
    none of this.

    Steps come in two groups. ``before`` is everything up to and including
    what the round's data said, which the centre column shows above the
    decision the round produced; ``after`` is the fit that followed the
    ruling, which it shows below.
    """
    r = int(round_id)
    pid = project or DEMO
    state = _state(pid)
    entry = next((e for e in state["rounds"]["rounds"] if int(e["round"]) == r), None)
    if entry is None or not entry.get("submission"):
        # Nothing was sent, so nothing happened that the page is not already
        # showing: a batch awaiting approval is rendered as the thing to do.
        return {"round": r, "steps": [], "reads": []}

    batch = project_mod.read_artifact(state, "batches", r)
    pool = project_mod.read_artifact(state, "candidates", r)
    snap = project_mod.read_artifact(state, "evidence", r)
    ev = project_mod.read_artifact(state, "batches", r, ".eval")
    run = project_mod.read_artifact(state, "models", r)
    sub = entry["submission"]
    lab = _lab_status(pid, r) or {}
    refs = [x for x in state["designs"]["external_refs"] if int(x["round"]) == r]
    steps, reads = [], []

    def read(path):
        if path not in reads:
            reads.append(path)

    if batch:
        read("batches/batch_%03d.json" % r)
        approval = batch["approval"]
        steps.append({
            "step": "proposed", "phase": "before", "at": None,
            "n": len(batch["approved"]), "mode": batch["mode"],
            "composition": batch["composition"], "hash": batch["hash"],
            "model_winner": batch["model_winner"], "from_round": r - 1,
            "policy": (batch.get("policy") or {}).get("round1_policy")
                      if batch["mode"] == "seed" else None,
            "n_enumerated": None if pool is None else pool["enumerated"],
            "n_feasible": None if pool is None else pool["feasible"],
            "incumbent": (None if batch["incumbent"] is None
                          else _figure(batch["incumbent"], "core.reconcile.pool",
                                       "batches/batch_%03d.json" % r, "incumbent",
                                       "pKD", synthetic=True)),
            "n_bridge": len(batch.get("bridge") or []),
            "n_fresh": len(batch.get("fresh") or []),
        })
        if pool is not None:
            read("candidates/pool_%03d.json" % r)
        steps.append({
            "step": "approved", "phase": "before", "at": approval.get("at"),
            "by": approval.get("by"), "status": approval["status"],
            "note": approval.get("note") or "",
            "n": len(batch["approved"]),
            "overrides": [{"design_id": o.get("design_id"), "note": o.get("note") or ""}
                          for o in (batch.get("overrides") or [])],
        })

    steps.append({
        "step": "submitted", "phase": "before", "at": lab.get("submitted"),
        "round_id": sub["round_id"], "registry": sub["registry"],
        "n_samples": sub["n_samples"], "assay_version": sub["assay_version"],
        "plates": sorted({x["plate"] for x in refs}),
        "n_constructs": len({x["construct_id"] for x in refs}),
        "order": (_order_csv(pid, r).replace(MOUNT + "/", "")
                  if os.path.exists(_order_csv(pid, r)) else None),
    })
    read("designs.json")

    if snap is not None:
        read("evidence/snapshot_%03d.json" % r)
        rec = snap["reconciliation"]
        steps.append({
            "step": "returned", "phase": "before", "at": None,
            "rows": rec["rows"], "samples": rec["samples"], "designs": rec["designs"],
            "n_ok": rec["n_ok"], "n_failed": rec["n_failed"],
            "n_censored": rec["n_censored"], "unreconciled": rec["unreconciled_rows"],
            "assay_version": snap["assay_version"],
            "source": (snap.get("source") or {}).get("file"),
            "plates": sorted({pl for m in snap["measurements"]
                              for pl in (m.get("plates") or [])}),
        })
        a = snap["anomaly"]
        cal = None if ev is None else ev["calibration"]
        imp = None if ev is None else ev["improvement"]
        # The two figures a fit is judged by are computed inside
        # evaluate_prior.py rather than by a core/ function of their own, so
        # they carry no source and render as plain numbers: the artifact they
        # were read from is named under the step and nothing claims more.
        steps.append({
            "step": "scored", "phase": "before", "at": None,
            "flagged": bool(snap["flagged"]),
            "scored_against_a_model": a is not None,
            "statistic": (None if a is None
                          else _figure(a["mean_signed_residual"],
                                       "core.reconcile.anomaly_flag",
                                       "evidence/snapshot_%03d.json" % r,
                                       "mean signed residual", "pKD")),
            "trigger": (None if a is None
                        else _figure(a["trigger_abs_pkd"], "core.reconcile.anomaly_flag",
                                     "objectives.json", "trigger", "pKD")),
            "n_compared": None if a is None else a["n_compared"],
            "z": None if a is None else a["z"],
            "known_version_offset": None if a is None else a["known_version_offset"],
            "assay_version": snap["assay_version"],
            "coverage": (None if cal is None
                         else _figure(cal["realized_coverage"], None,
                                      "batches/batch_%03d.eval.json" % r,
                                      "realized coverage")),
            "nominal_coverage": None if cal is None else cal["nominal_coverage"],
            "best": (None if imp is None or imp["best_this_round"] is None
                     else _figure(imp["best_this_round"], None,
                                  "batches/batch_%03d.eval.json" % r,
                                  "best this round", "pKD", synthetic=True)),
            "gain": (None if imp is None or imp["gain_over_incumbent"] is None
                     else _figure(imp["gain_over_incumbent"], None,
                                  "batches/batch_%03d.eval.json" % r,
                                  "gain over the incumbent", "pKD", synthetic=True)),
        })
        if ev is not None:
            read("batches/batch_%03d.eval.json" % r)
        frame = snap["frame"]
        if frame.get("offset_applied"):
            steps.append({
                "step": "frame", "phase": "before", "at": None,
                "offset": _figure(frame["offset_applied"],
                                  "core.reconcile.offset_from_bridge",
                                  "evidence/snapshot_%03d.json" % r, "frame offset", "pKD"),
                "authority": frame["authority"],
                "n_bridge": (frame.get("offset_estimate") or {}).get("n"),
            })

    if run is not None:
        read("models/run_%03d.json" % r)
        nxt = next((e for e in state["rounds"]["rounds"] if int(e["round"]) == r + 1), None)
        steps.append({
            "step": "fitted", "phase": "after", "at": None,
            "winner": run["winner"], "n_observations": run["n_observations"],
            "hash": run["hash"],
            "recipes": {k: {"nlpd": v.get("nlpd"), "rmse": v.get("rmse"),
                            "coverage_80": v.get("coverage_80")}
                        for k, v in run["recipes"].items()},
            "next_round": None if nxt is None else int(nxt["round"]),
        })
    return {"round": r, "steps": steps, "reads": reads,
            "source": "the round's own artifacts; no command in this browser produced them"}


QUESTIONS = {
    "where_are_we": "Where are we?",
    "whats_waiting": "What's waiting on me?",
    "why_flagged": "Why did round %s flag?",
    "results_back": "Have round %s's results come back?",
    "what_is_this": "What does this template actually declare?",
}


def _briefing(pid, key, round_id):
    """Assemble one answer. Reads artifacts; computes nothing."""
    state = _state(pid)
    entries = state["rounds"]["rounds"]
    rounds = [_round_view(state, e, pid) for e in entries]
    progress = _cumulative_best(state)
    question = QUESTIONS.get(key, key)
    if "%s" in question:
        question = question % round_id

    base = {"key": key, "question": question, "project": pid, "round": round_id,
            "reads": []}

    if key == "where_are_we":
        latest = progress[-1] if progress else None
        scored = [r for r in rounds if r["status"] != "not started"]
        winner = next((r["model"]["winner"] for r in reversed(rounds) if r["model"]), None)
        moves = [{"round": r["round"],
                  "offset": _figure(r["frame"]["offset_applied"],
                                    "core.reconcile.offset_from_bridge",
                                    "evidence/snapshot_%03d.json" % r["round"],
                                    "frame offset", "pKD"),
                  "authority": r["frame"]["authority"]}
                 for r in rounds if r["frame"] and r["frame"]["offset_applied"]]
        return dict(base, kind="status",
                    n_rounds=len(entries), n_scored=len(scored),
                    n_designs=len(state["designs"]["designs"]),
                    best_observed=(_figure(latest["best_observed"], "core.reconcile.pool",
                                           "evidence/snapshot_%03d.json" % latest["round"],
                                           "best observed", "pKD", synthetic=True)
                                   if latest else None),
                    n_measured=latest["n_measured"] if latest else 0,
                    rounds=[{"round": r["round"], "status": r["status"],
                             "flagged": r["flagged"], "verdict": r["verdict"],
                             "at_lab": r["at_lab"]} for r in rounds],
                    frame_moves=moves, model_winner=winner,
                    reads=["rounds.json", "designs.json"]
                          + ["evidence/snapshot_%03d.json" % r["round"]
                             for r in rounds if r["refs"].get("snapshot")])

    if key == "whats_waiting":
        waiting = []
        for r in rounds:
            if r["status"] == "flagged, ruling pending":
                dec = project_mod.read_decision(state, r["round"])
                waiting.append({"round": r["round"], "kind": "ruling",
                                "detail": ("%d hypotheses, %s recommended"
                                           % (len(dec["hypotheses"]),
                                              dec["recommendation"]["action"])
                                           if dec else "no diagnosis proposed yet")})
            elif r["status"] == "awaiting approval":
                waiting.append({"round": r["round"], "kind": "approval",
                                "detail": "%d wells, %s"
                                          % (r["batch"]["n"], r["batch"]["mode"])})
            elif r["at_lab"]:
                waiting.append({"round": r["round"], "kind": "at the lab",
                                "detail": "submitted %s, expected %s"
                                          % ((r["lab"]["submitted"] or "?")[:10],
                                             (r["lab"]["expected"] or "?")[:10])})
        return dict(base, kind="waiting", items=waiting,
                    reads=["rounds.json"] + ["decisions/decision_%03d.json" % w["round"]
                                             for w in waiting if w["kind"] == "ruling"])

    if key == "why_flagged":
        r = next((x for x in rounds if x["round"] == int(round_id)), None)
        if r is None or not r["anomaly"]:
            return dict(base, kind="none",
                        detail="round %s has no snapshot to read" % round_id)
        a = r["anomaly"]
        obj = state["objectives"]["anomaly_flag"]
        return dict(base, kind="flag",
                    flagged=bool(r["flagged"]),
                    statistic=_figure(a["mean_signed_residual"],
                                      "core.reconcile.anomaly_flag",
                                      "evidence/snapshot_%03d.json" % r["round"],
                                      "mean signed residual", "pKD"),
                    trigger=_figure(a["trigger_abs_pkd"], "core.reconcile.anomaly_flag",
                                    "objectives.json", "trigger", "pKD"),
                    n_compared=a["n_compared"], z=a["z"], se=a["se"],
                    direction=a["direction"], assay_version=a["assay_version"],
                    known_version_offset=a["known_version_offset"],
                    policy_note=obj.get("note"),
                    decision_status=r["decision_status"],
                    reads=["evidence/snapshot_%03d.json" % r["round"], "objectives.json"])

    if key == "results_back":
        r = next((x for x in rounds if x["round"] == int(round_id)), None)
        lab = (r or {}).get("lab")
        return dict(base, kind="lab",
                    submitted=(lab or {}).get("submitted"),
                    expected=(lab or {}).get("expected"),
                    status=(lab or {}).get("status", "not submitted"),
                    note="the registry owns this answer; asking it is a tool call",
                    reads=["lims_store/%s.json" % pid])

    if key == "what_is_this":
        obj = state["objectives"]
        return dict(base, kind="template",
                    template=state["project"]["template"],
                    editable_region=obj["editable_region"],
                    constraints=obj["constraints"],
                    objectives=obj["objectives"],
                    batch=obj["batch"], recipes=obj["model_recipes"],
                    diagnostics=obj["diagnostics"],
                    anomaly_flag=obj["anomaly_flag"],
                    objectives_hash=obj["hash"],
                    reads=["objectives.json", "project.json"])

    return dict(base, kind="none", detail="no briefing for %r" % key)


# --- the agent's seat ------------------------------------------------------
#
# Phase 7. A model sits in the centre column and chooses which test to run
# next; nothing here changes what a test is or what it returns. Three things
# below serve that seat, and each obeys the rule this file already has.
#
# **What the model is given is read, never narrated.** ``agent_context``
# assembles the project's own artifacts -- objectives, the round graph, the
# focus round's batch scored against what came back, every decision record --
# into one typed blob the page sends with the question. No sentence in it is
# this file's; the numbers are the ones already on disk.
#
# **The sixth question runs here, and it is a guard and not a sandbox.**
# ``execute_analysis`` runs model-written numpy read-only against the mounted
# snapshot arrays, with a line budget, a read-only ``open``, an import
# denylist and a token check for the two directories it may not touch. That
# is the same posture as the gate's ``data/`` rule -- decision 97 -- and it
# is stated as such rather than dressed up: the oracle ships in this bundle
# because the simulated laboratory has to run client-side, and anyone can
# read it by URL. The claim is that ``core/`` never does, and that ad hoc
# output is evidence a person reads and never an input to a code path, which
# ``record_decision.py`` enforces on its own.
#
# **Replay is the recorded record stepped, with every number recomputed.**
# ``replay_plan`` reads the shipped proposal -- claims, tests, readings,
# reasoning, and no results -- and ``verify_diagnostic`` compares what this
# browser computed against the committed record by content hash. The page
# never renders a reference number; it renders the recomputed one and says
# whether it matched.


AD_HOC_LINE_BUDGET = 2_000_000
# Modules an ad hoc analysis may not import, and strings it may not mention.
# The first list is the simulated laboratory and this driver; the second is
# the machinery a ten-line numpy cut has no business reaching for.
AD_HOC_DENIED_MODULES = ("data", "lims", "wb_driver", "subprocess", "shutil", "socket",
                         "urllib", "http", "ctypes", "importlib", "pyodide", "js")
AD_HOC_DENIED_TOKENS = ("data/", "data.oracle", "data.synthetic", "landscape.npz",
                        "landscape_manifest", "os.remove", "os.rename",
                        "os.unlink", "rmtree", "__import__", "sys.modules", "settrace",
                        "builtins")
# What a cut may read besides the project: the round's own results export,
# where the registry writes a pull. The registry's records beside it are not
# the workbench's to read, and the oracle never is.
AD_HOC_READABLE = ("projects", os.path.join("lims_store", "exports"), "templates", "core")


def _ad_hoc_path(project_id, n):
    return os.path.join(_session_dir(project_id), "ad_hoc_%03d.py" % n)


def _guarded_builtins():
    """``open`` that only reads, ``__import__`` with a denylist, nothing else changed."""
    import builtins                                          # noqa: PLC0415
    real_open, real_import = builtins.open, builtins.__import__

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(c in str(mode) for c in "wax+"):
            raise PermissionError("ad hoc analysis is read-only; it cannot open %r for "
                                  "writing" % file)
        full = os.path.abspath(os.path.join(os.getcwd(), str(file)))
        if not any(full.startswith(os.path.join(MOUNT, ok) + os.sep) for ok in AD_HOC_READABLE):
            raise PermissionError(
                "ad hoc analysis reads the project directory and the round's results "
                "export (lims_store/exports/), by relative path; not %r" % str(file))
        return real_open(file, mode, *args, **kwargs)

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in AD_HOC_DENIED_MODULES:
            raise ImportError("ad hoc analysis may not import %r" % name)
        return real_import(name, *args, **kwargs)

    ns = dict(vars(builtins))
    ns["open"] = guarded_open
    ns["__import__"] = guarded_import
    return ns


def execute_analysis(code, project=None, round_id=None, session=None, question=None,
                     verify=None):
    """Run model-written numpy read-only against the mounted arrays.

    The code is written to ``session/<project>/ad_hoc_NNN.py`` first, so the
    command the log shows names a file that exists and ran. Output is
    captured; a line budget stops a runaway loop from freezing the tab, which
    is the one thing the main thread cannot otherwise recover from.
    """
    pid = project or DEMO
    code = str(code or "")
    if not code.strip():
        raise ValueError("execute_analysis needs code to run")
    lowered = code.lower()
    hit = next((t for t in AD_HOC_DENIED_TOKENS if t in lowered), None)
    if hit is not None:
        raise PermissionError("ad hoc analysis may not mention %r: the simulated "
                              "laboratory and the registry's own records are off limits"
                              % hit)

    os.makedirs(_session_dir(pid), exist_ok=True)
    n = len(_log_read(pid)["entries"]) + 1
    path = _ad_hoc_path(pid, n)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code.rstrip("\n") + "\n")

    out, msg = io.StringIO(), io.StringIO()
    err, lines = None, [0]

    def tracer(frame, event, arg):
        if event == "line":
            lines[0] += 1
            if lines[0] > AD_HOC_LINE_BUDGET:
                raise RuntimeError("ad hoc analysis exceeded its budget of %d lines"
                                   % AD_HOC_LINE_BUDGET)
        return tracer

    cwd = os.getcwd()
    os.chdir(MOUNT)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(msg):
            ns = {"__name__": "__ad_hoc__", "__builtins__": _guarded_builtins()}
            sys.settrace(tracer)
            try:
                exec(compile(code, os.path.relpath(path, MOUNT), "exec"), ns)  # noqa: S102
            finally:
                sys.settrace(None)
    except Exception:                                        # noqa: BLE001 - shown
        err = traceback.format_exc(limit=2)
    finally:
        os.chdir(cwd)

    entry = _log_append(pid, {
        "kind": "adhoc",
        "tool": "execute_analysis",
        "round": None if round_id is None else int(round_id),
        "session": session,
        "command": "python %s" % os.path.relpath(path, MOUNT),
        "label": "ad hoc: %s" % (question or "one-off analysis")[:80],
        "note": "one-off, unversioned; evidence a human reads, never an input to a code path",
        "code": 0 if err is None else 1,
        "refused": False,
        "output": out.getvalue().rstrip("\n"),
        "messages": (msg.getvalue() + (err or "")).rstrip("\n"),
        "source": code,
    })
    out = {"ok": err is None, "stdout": entry["output"], "stderr": entry["messages"],
           "lines": lines[0], "path": os.path.relpath(path, MOUNT), "log": entry}
    if verify and round_id is not None:
        out["verified"] = _verify_ad_hoc(int(round_id), verify.get("pass", 1),
                                         int(verify.get("index", 0)), entry["output"], pid)
    return out


def _scalars(result):
    """The flat numbers in a diagnostic result, for a context that should not
    carry every per-design list twice."""
    return {k: v for k, v in (result or {}).items()
            if v is None or isinstance(v, (int, float, str, bool))}


def _decision_context(dec):
    """A decision record as the model reads it: every pass, results flattened."""
    passes = []
    for p in dec.get("passes", []):
        passes.append({
            "pass": p["pass"], "at": p.get("at"), "answering": p.get("answering"),
            "hypotheses": [{
                "id": h["id"], "claim": h["claim"], "diagnostic": h["diagnostic"],
                "args": h.get("args") or {}, "reading": h["reading"],
                "reasoning": h.get("reasoning"), "source": h.get("source"),
                "result": _scalars(h.get("result")),
                "result_groups": {k: v for k, v in (h.get("result") or {}).items()
                                  if isinstance(v, dict) and k in ("by_plate", "classes",
                                                                    "by_bin", "bins")},
            } for h in p["hypotheses"]],
            "ad_hoc": [{"question": a["question"], "stdout": a.get("stdout")}
                       for a in p.get("ad_hoc", [])],
            "recommendation": p["recommendation"],
            "ruling": p.get("ruling"),
        })
    return {"id": dec["id"], "round": dec["round"], "status": dec["status"],
            "trigger": dec["trigger"], "n_passes": dec.get("n_passes", len(passes)),
            "passes": passes, "inputs": dec.get("inputs")}


def _batch_context(state, r):
    """The focus round's wells: what was predicted, what came back, per design."""
    batch = project_mod.read_artifact(state, "batches", r)
    if batch is None:
        return None
    snap = project_mod.read_artifact(state, "evidence", r)
    ev = project_mod.read_artifact(state, "batches", r, ".eval")
    designs = project_mod.designs_by_id(state)
    measured = {m["design_id"]: m for m in (snap or {}).get("measurements", [])}
    scored = {p["design_id"]: p for p in (ev or {}).get("per_design", [])}
    rows = []
    for s in batch["slots"]:
        d = designs.get(s["design_id"], {})
        m = measured.get(s["design_id"])
        p = scored.get(s["design_id"])
        rows.append({
            "design_id": s["design_id"],
            "mutations": d.get("mutations", []),
            "slot": s["slot"], "plate": s.get("plate_planned"),
            "pred_mean": s.get("pred_mean"), "pred_sd": s.get("pred_sd"),
            "expected_improvement": s.get("expected_improvement"),
            "extrapolation": bool(s.get("extrapolation")),
            "bridge": bool(s.get("bridge")),
            "fresh": None if m is None else bool(m.get("fresh")),
            "status": None if m is None else m.get("status"),
            "observed": None if m is None else m.get("value"),
            "read_sd": None if m is None else m.get("read_sd"),
            "plates": None if m is None else m.get("plates"),
            "residual": None if p is None else p.get("residual"),
            "inside_interval": None if p is None else p.get("inside_interval"),
        })
    return {
        "round": r, "hash": batch["hash"], "mode": batch["mode"],
        "model_winner": batch["model_winner"], "incumbent": batch["incumbent"],
        "composition": batch["composition"], "approval": batch["approval"],
        "n_overridden": len(batch.get("overrides") or []),
        "rows": rows,
    }


def agent_context(project=None, round_id=None):
    """Everything the model in the centre seat is handed, read from disk.

    This is the ~20k-token stable prefix the design calls for: the objectives,
    the round graph with every round's anomaly, frame, calibration and model
    summary, the focus round's batch table scored against what came back,
    and every decision record with every pass. It computes nothing -- each
    figure is the one an artifact already holds -- and it names the paths an
    ad hoc analysis would read, relative to the mount the code runs in.
    """
    pid = project or DEMO
    state = _state(pid)
    entries = state["rounds"]["rounds"]
    rounds = [_round_view(state, e, pid) for e in entries]
    focus = int(round_id) if round_id is not None else (rounds[-1]["round"] if rounds else None)

    decisions = []
    for e in entries:
        dec = project_mod.read_decision(state, int(e["round"]))
        if dec is not None:
            decisions.append(_decision_context(dec))

    obj = dict(state["objectives"])
    return {
        "project": {
            "id": pid, "lead": state["project"]["lead"], "target": state["project"]["target"],
            "team": state["project"]["team"], "template": state["project"]["template"],
            "root": "projects/%s" % pid,
        },
        "objectives": obj,
        # The lab line is what the seat used to be missing. Without it a model
        # asked whether a round had come back could only report what the
        # project's own files said -- "still marked at the lab" -- and had to
        # say it could not check. `_lab_status` peeks rather than asks, so
        # assembling the context never releases a held round; asking is still
        # a tool call the model makes on purpose.
        "rounds": [dict({k: v for k, v in r.items() if k not in ("lab", "order", "refs")},
                        lab=None if not r["lab"] else {
                            k: r["lab"][k] for k in
                            ("status", "submitted", "expected", "assay_version",
                             "n_samples", "n_rows", "released_by")})
                   for r in rounds],
        "progress": _cumulative_best(state),
        "focus_round": focus,
        "batch": None if focus is None else _batch_context(state, focus),
        "decisions": decisions,
        # What the seat may ask to change, and the bounds it will be held to.
        # Read out of core/amend.py rather than described, so the prompt and
        # the writer cannot disagree about it -- and the current value comes
        # off the project, because a proposal has to know what it is moving
        # from even though it never gets to say so.
        "amendable": {
            "fields": [{
                "field": f,
                "now": amend.current(obj, f),
                "kind": kind, "low": low, "high": high,
                "moves_the_pool": f in amend.POOL_FIELDS,
            } for f, (kind, low, high) in sorted(amend.AMENDABLE.items())],
            "min_fresh_picks": amend.MIN_FRESH_PICKS,
            "max_feasible_pool": amend.MAX_FEASIBLE_POOL,
            "amendments": obj.get("amendments") or [],
            "note": "one field per proposal, on the recommendation's `amendment`. The "
                    "bounds are enforced in code before the record is written, and nothing "
                    "is applied until a named person rules -- who may dial the number. "
                    "Everything else in objectives.json is the template's declaration and "
                    "is not amendable from this seat",
        },
        "tests": {
            "permitted": obj["diagnostics"],
            "arguments": {
                "scope": ["all", "fresh"],
                "by": ["position", "n_mutations"],
                "offset": ["none", "bridge"],
            },
            "policy": obj.get("diagnostics_policy"),
        },
        "paths": {
            "cwd": ".",
            "snapshot": (None if focus is None
                         else "projects/%s/evidence/snapshot_%03d.json" % (pid, focus)),
            "batch": (None if focus is None
                      else "projects/%s/batches/batch_%03d.json" % (pid, focus)),
            "evaluation": (None if focus is None
                           else "projects/%s/batches/batch_%03d.eval.json" % (pid, focus)),
            "designs": "projects/%s/designs.json" % pid,
            "rounds": "projects/%s/rounds.json" % pid,
            "results_export": (None if focus is None
                               else "lims_store/exports/%s_round%d.csv" % (pid, focus)),
            # The first live run spent two turns discovering that a batch file
            # holds `slots` and not the `rows` this context summarizes it as.
            # One line each saves the discovery, and it describes files that
            # are what they are.
            "shapes": {
                "snapshot": "measurements[]: design_id, value, raw_value, status, censored, "
                            "plates[], fresh, bridge, read_sd, n_ok; plus anomaly, frame",
                "batch": "slots[]: design_id, slot, plate_planned, pred_mean, pred_sd, "
                         "expected_improvement, extrapolation, bridge, rationale; plus "
                         "approved[], composition, incumbent",
                "evaluation": "per_design[]: design_id, observed, pred_mean, pred_sd, "
                              "residual, inside_interval, slot; plus calibration, improvement",
                "designs": "designs[]: design_id, sequence, mutations[], n_mutations, parent; "
                           "external_refs[]: design_id, round, sample_id, construct_id",
                "results_export": "CSV: sample_id, plate, well, assay_version, replicate, "
                                  "value, unit, status -- join to designs via external_refs",
            },
        },
        "synthetic": "every affinity value here is generated by a synthetic landscape and "
                     "read through a simulated assay; say so beside any number you quote",
    }


# Agent turns are stored in the same per-session record the asks use, so a
# reload shows the diagnosis that ran rather than a blank column. Each turn
# is upserted whole by its id as it progresses; the tool calls it made are in
# the log already and are referenced by their `n`.
#
# Every turn carries ``after_n``, the log's length when it began, the same
# stamp ``ask`` puts on its turns. The column is one stream in the order
# things happened, and this is how a turn is placed in it against the commands
# that ran before and after it. The first save is the one that stamps it,
# because a turn is saved before its first tool call runs.


def agent_turn_save(session_id, turn, project=None, at=None):
    """Upsert one agent turn into its session's record."""
    pid = project or DEMO
    doc = _adhoc_read(pid)
    rec = next((s for s in doc["sessions"] if s["id"] == session_id), None)
    if rec is None:
        rec = {"id": session_id, "kind": "round" if _is_round(session_id) else "adhoc",
               "title": None, "created": at or "", "updated": at or "", "turns": []}
        doc["sessions"].append(rec)
    turn = dict(turn)
    turn["kind"] = "agent"
    slot = next((i for i, t in enumerate(rec["turns"])
                 if t.get("kind") == "agent" and t.get("id") == turn.get("id")), None)
    if slot is None:
        turn.setdefault("after_n", len(_log_read(pid)["entries"]))
        rec["turns"].append(turn)
    else:
        turn.setdefault("after_n", rec["turns"][slot].get("after_n"))
        rec["turns"][slot] = turn
    rec["updated"] = at or rec.get("updated") or ""
    if not rec.get("title") and not _is_round(session_id) and turn.get("question"):
        rec["title"] = (turn.get("label") or turn["question"])[:80]
    _adhoc_write(pid, doc)
    return turn


def replay_plan(round_id, project=None):
    """The recorded diagnosis for a round, with no numbers in it.

    Read from the shipped proposal -- the committed record with every result,
    source and input hash stripped by ``web/bundle.py`` -- so what the page
    steps is the agent's claims, its choice of test for each, its readings
    and its recommendation. The tests run here; the numbers come from them.
    """
    r = int(round_id)
    pid = project or DEMO
    if pid != DEMO:
        return None
    plan = reference("decision_%03d.proposal.json" % r)
    if plan is None:
        return None
    return plan


def _verify_diagnostic(round_id, pass_no, hypothesis_id, result, project=None):
    """Did this browser get what the committed record got? A hash, not a number."""
    r = int(round_id)
    pid = project or DEMO
    ref = reference("decision_%03d.json" % r) if pid == DEMO else None
    if ref is None:
        return {"checked": False, "matched": None}
    passes = ref.get("passes") or []
    p = next((p for p in passes if int(p["pass"]) == int(pass_no)), None)
    h = next((h for h in (p or {}).get("hypotheses", []) if h["id"] == hypothesis_id), None)
    if h is None:
        return {"checked": False, "matched": None}
    return {"checked": True,
            "matched": schema.content_hash(result) == schema.content_hash(h["result"]),
            "reference_hash": schema.content_hash(h["result"])}


def verify_record(round_id, pass_no=None, project=None):
    """Every result in one pass of this round's record, against the reference.

    The record on disk was written by ``record_decision.py`` here, so its
    numbers are this browser's; the reference is the committed record. A hash
    per hypothesis, and the count that agree.
    """
    r = int(round_id)
    pid = project or DEMO
    dec = project_mod.read_decision(_state(pid), r)
    if dec is None:
        return {"checked": False, "matched": 0, "total": 0}
    passes = dec.get("passes") or []
    n = int(pass_no) if pass_no is not None else len(passes)
    p = next((x for x in passes if int(x["pass"]) == n), None)
    if p is None:
        return {"checked": False, "matched": 0, "total": 0}
    out = [_verify_diagnostic(r, n, h["id"], h["result"], pid) for h in p["hypotheses"]]
    return {"checked": all(v["checked"] for v in out), "pass": n,
            "matched": sum(1 for v in out if v["matched"]), "total": len(out)}


def _verify_ad_hoc(round_id, pass_no, index, stdout, project=None):
    """Did the committed ad hoc code print the same thing here?"""
    r = int(round_id)
    pid = project or DEMO
    ref = reference("decision_%03d.json" % r) if pid == DEMO else None
    if ref is None:
        return {"checked": False, "matched": None}
    p = next((p for p in ref.get("passes") or [] if int(p["pass"]) == int(pass_no)), None)
    items = (p or {}).get("ad_hoc", [])
    if index >= len(items):
        return {"checked": False, "matched": None}
    return {"checked": True,
            "matched": (items[index].get("stdout") or "").strip() == (stdout or "").strip()}


# --- files the visitor can take away ---------------------------------------


def download(path):
    """Hand a file out of the Pyodide filesystem to the page, as text.

    The order file is a real export the visitor can open in a spreadsheet, so
    it is read back out of the same filesystem the registry wrote it to rather
    than rebuilt for display.
    """
    full = os.path.join(MOUNT, path.lstrip("/"))
    if not os.path.abspath(full).startswith(MOUNT + os.sep):
        raise ValueError("outside the mount: %r" % path)
    if not os.path.isfile(full):
        raise ValueError("no such file: %r" % path)
    with open(full, encoding="utf-8") as fh:
        return {"path": path, "name": os.path.basename(full), "text": fh.read()}


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


def ensure_dirs():
    """Re-assert the directory skeleton the overlay cannot carry.

    ``dump_state`` returns files, so the overlay is a map of path to contents
    and a directory with nothing in it yet does not survive a reload. A
    project instantiated in this browser has five of them until its first
    round writes into each, so the reload that follows its creation finds
    ``project.json`` and no ``evidence/`` -- and ``snapshots`` raises before
    the home screen can list anything, including the shipped campaign.

    The skeleton is derivable rather than state: every project directory has
    the same subdirectories, named once in ``schema.SUBDIRS``. Boot re-asserts
    them instead of the overlay storing them, and nothing here writes a byte
    into a file, so no artifact and no hash moves.
    """
    out = []
    if not os.path.isdir(PROJECTS_DIR):
        return out
    for name in sorted(os.listdir(PROJECTS_DIR)):
        root = os.path.join(PROJECTS_DIR, name)
        if not os.path.isfile(os.path.join(root, "project.json")):
            continue
        missing = [d for d in schema.SUBDIRS
                   if not os.path.isdir(os.path.join(root, d))]
        if missing:
            schema.ensure_project_dirs(root)
            out.append({"project": name, "created": missing})
    return out


def dump_state():
    """Every mutable file, so the page can put the visitor's progress away."""
    out = {}
    for root in (PROJECTS_DIR, STORE_DIR, SESSIONS_DIR):
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
