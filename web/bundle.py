#!/usr/bin/env python3
"""Assemble everything the browser needs, from the repository's own files.

    python web/bundle.py            # write web/public/workbench/
    python web/bundle.py --check    # verify the written bundle is current

Two jobs, and both exist to stop the browser from becoming a second
implementation of anything -- CLAUDE.md non-negotiable 2.

**Copy, never port.** The bundle is `core/`, `data/`, `lims.py` and the seven
skill scripts, byte for byte, laid out in the same directory shape so that
every `sys.path` walk and every `dirname(__file__)` inside them resolves the
way it does on a laptop. Pyodide then runs the same modules the CLI runs. A
manifest records a sha256 per file so `check.py` can prove the copies have not
drifted, and so the page can show which commit's science it is executing.

**Derive the demo state, never hand-write it.** The browser opens on the
committed project rewound to the moment before round 4 was approved -- rounds
1-3 complete and ruled, round 4's pool and batch selected and waiting on a
person. Round 4's post-submission artifacts are removed, and its batch is then
re-selected by `select_batch.py` with no approver named, because approving is
what the visitor is here to do.

**An unapproved batch has no timestamp in it, and that is what makes the hash
claim checkable.** `--approved-by` stamps `approval.at`, so an approved batch
record can never be reproduced on a second machine. Without it the record is a
pure function of the pool, the model run and the objectives, and every surface
that selects that batch prints the same hash. The bundle therefore ships the
unapproved record, asserts it differs from the committed one in `approval` and
`hash` and nothing else, and then replays round 4 forward through the real
LIMS and `import_round.py` and requires the returned snapshot to match the
committed one everywhere except the batch pointer it necessarily carries.

The proposal payload is derived the same way: the committed `decision_004.json`
with every `result`, `source` and `inputs` block stripped out, and every ad hoc
cut's stdout with them, pass by pass. What ships is the agent's claims, its
choice of tests and its reasoning, the ruling that sent it back, and no
numbers. The browser re-runs every diagnostic through `core.diagnostics`, runs
every cut again, and `record_decision.py` fills the results back in. A number
that appeared in the browser without being recomputed there would be exactly
the failure mode non-negotiable 7 exists to prevent.

**The model's system prompt is the skill, and it is copied here too.** Phase 7
puts a model behind `web/function/ask.mjs`, and what that function
hands it is `skills/adaptive-optimization/SKILL.md` -- the same file Claude
Code and Claude Science load -- written into `web/function/lib/skill.mjs`
as a string with its sha256 beside it, because a function bundler carries a
module and not a path. `check.py` requires the string to be the file.
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from core import project, schema  # noqa: E402

OUT = os.path.join(REPO, "web", "public", "workbench")
DEMO = "demo-trastuzumab"

# Code the browser executes. Copied verbatim, in repo layout.
CODE = [
    "core/__init__.py", "core/schema.py", "core/encode.py", "core/scoring.py",
    "core/candidates.py", "core/surrogate.py", "core/acquisition.py",
    "core/reconcile.py", "core/diagnostics.py", "core/project.py",
    "data/__init__.py", "data/synthetic.py", "data/oracle.py",
    "data/landscape_manifest.json",
    "lims.py",
    "init_project.py",
    "skills/adaptive-optimization/scripts/generate_candidates.py",
    "skills/adaptive-optimization/scripts/select_batch.py",
    "skills/adaptive-optimization/scripts/import_round.py",
    "skills/adaptive-optimization/scripts/evaluate_prior.py",
    "skills/adaptive-optimization/scripts/fit_surrogates.py",
    "skills/adaptive-optimization/scripts/run_diagnostic.py",
    "skills/adaptive-optimization/scripts/record_decision.py",
    "templates/antibody-affinity-maturation/template.json",
    "templates/enzyme-thermostability/template.json",
]

# The driver, which lives under web/ because it is the browser's and nobody
# else's. It calls the scripts above through their main(argv); it computes
# nothing.
DRIVER = "web/py/wb_driver.py"

# The skill, which is the model's system prompt on every surface. The function
# bundler ships modules, so the file becomes a module carrying the file.
SKILL = "skills/adaptive-optimization/SKILL.md"
SKILL_MODULE = "web/function/lib/skill.mjs"

# The shipped campaign spans weeks, because a campaign that does not is not a
# campaign. The project was generated in one sitting, so every round carries
# the afternoon it was written; left alone the rail dates rounds 1 to 4 "today"
# and visibly contradicts the six-week story the pitch rests on.
#
# This touches `updated` and nothing else -- the times the round graph was
# rewritten, which check.py already excludes from byte-identity for exactly
# that reason. No measurement, no hash input and no artifact body moves. The
# registry's turnaround (lims.TURNAROUND_DAYS) is set to agree with the
# spacing, so a round submitted here and expected there tell one story.
ROUND_SPACING_DAYS = 11
CAMPAIGN_STARTED_DAYS_AGO = 44

# Rewind point: everything round 4 gained at or after submission.
ROUND4_ARTIFACTS = [
    "evidence/snapshot_004.json",
    "batches/batch_004.eval.json",
    "decisions/decision_004.json",
]
# What a round entry holds before its batch goes to the lab.
PRE_SUBMIT_KEYS = ("round", "pool", "batch", "updated")


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def copy(rel, dest_root):
    src = os.path.join(REPO, rel)
    dst = os.path.join(dest_root, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def rewind_project(dest_root):
    """The committed project, minus everything round 4 gained from the lab."""
    src = os.path.join(REPO, "projects", DEMO)
    dst = os.path.join(dest_root, "projects", DEMO)
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    for rel in ROUND4_ARTIFACTS:
        path = os.path.join(dst, rel)
        if os.path.exists(path):
            os.remove(path)

    rounds = schema.read_json(os.path.join(dst, "rounds.json"))
    for entry in rounds["rounds"]:
        if int(entry["round"]) == 4:
            for key in [k for k in entry if k not in PRE_SUBMIT_KEYS]:
                del entry[key]
    redate_rounds(rounds)
    rounds = schema.stamp({k: v for k, v in rounds.items() if k != "hash"})
    schema.write_json(os.path.join(dst, "rounds.json"), rounds)

    # designs.json keeps every design -- round 4's were designed before it was
    # submitted -- and loses only what the registry gave back.
    designs = schema.read_json(os.path.join(dst, "designs.json"))
    minted_later = {r["design_id"] for r in designs["external_refs"] if int(r["round"]) == 4}
    minted_before = {r["design_id"] for r in designs["external_refs"] if int(r["round"]) < 4}
    designs["external_refs"] = [r for r in designs["external_refs"] if int(r["round"]) < 4]
    for d in designs["designs"]:
        if d["design_id"] in minted_later and d["design_id"] not in minted_before:
            d["registry_id"] = None
    designs = schema.stamp({k: v for k, v in designs.items() if k != "hash"})
    schema.write_json(os.path.join(dst, "designs.json"), designs)
    return dst, minted_later - minted_before


def redate_rounds(rounds):
    """Spread the round graph's `updated` stamps over a plausible campaign.

    Round 1 lands about six weeks back and each round after it eleven days
    later, which is roughly a build, an eight-day assay and a week of
    deciding. The last round keeps a recent date because it is the one the
    visitor is being asked about.
    """
    base = (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=CAMPAIGN_STARTED_DAYS_AGO)).replace(microsecond=0)
    for i, entry in enumerate(rounds["rounds"]):
        if "updated" in entry:
            entry["updated"] = (base + datetime.timedelta(
                days=i * ROUND_SPACING_DAYS)).isoformat()
    return rounds


def rewind_store(dest_root, minted_at_round4):
    """The registry's own records, minus the round it has not been sent yet."""
    src = os.path.join(REPO, "lims_store", "%s.json" % DEMO)
    store = schema.read_json(src)
    store["rounds"] = {k: v for k, v in store["rounds"].items() if k != "R4"}
    kept = {k: v for k, v in store["constructs"].items() if k not in minted_at_round4}
    dropped = len(store["constructs"]) - len(kept)
    store["constructs"] = kept
    store["next_construct"] -= dropped
    # The registry's own dates move with the graph's, so `check_run_status` on
    # an old round does not report it submitted this afternoon.
    rounds = schema.read_json(os.path.join(dest_root, "projects", DEMO, "rounds.json"))
    when = {int(e["round"]): e.get("updated") for e in rounds["rounds"]}
    for key, rec in store["rounds"].items():
        stamp = when.get(int(rec["round"]))
        if stamp:
            rec["submitted"] = stamp
    dst = os.path.join(dest_root, "lims_store", "%s.json" % DEMO)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    schema.write_json(dst, store)
    return dst


def proposal_payload():
    """decision_004, with every number taken back out of it.

    What survives is what the agent contributed: the claims, which test it
    chose for each, how it read the answer, and the recommendation -- for
    every pass the record went through, with the ruling that sent it back
    between them. The browser recomputes the rest: each test through
    ``run_diagnostic.py``, each ad hoc cut by running its code again, which
    is why the cut's ``stdout`` is stripped along with the results.
    """
    rec = schema.read_json(os.path.join(REPO, "projects", DEMO, "decisions",
                                        "decision_004.json"))
    passes = []
    for p in rec["passes"]:
        ruling = p.get("ruling")
        passes.append({
            "pass": p["pass"],
            "answering": p.get("answering"),
            "hypotheses": [{
                "id": h["id"],
                "claim": h["claim"],
                "diagnostic": h["diagnostic"],
                "args": h.get("args") or {},
                "reading": h["reading"],
                "reasoning": h["reasoning"],
            } for h in p["hypotheses"]],
            "ad_hoc": [{"question": a["question"], "code": a["code"]}
                       for a in p.get("ad_hoc", [])],
            "recommendation": p["recommendation"],
            "ruling": None if ruling is None else {
                "verdict": ruling["verdict"], "by": ruling["by"], "note": ruling["note"],
                "requested": ruling.get("requested"),
            },
        })
    return {
        "note": ("the committed round-4 proposal with every result, source, input hash "
                 "and ad hoc stdout removed. record_decision.py re-runs each named test "
                 "in the browser, execute_analysis re-runs each cut, and the numbers are "
                 "filled back in there"),
        "source_record": rec["hash"],
        "round": rec["round"],
        "trigger": rec["trigger"],
        "n_passes": rec["n_passes"],
        "passes": passes,
    }


SCRIPTS = os.path.join(REPO, "skills", "adaptive-optimization", "scripts")


def run(argv, where=None):
    r = subprocess.run([sys.executable] + argv, cwd=where or REPO,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("step failed: %s\n%s" % (" ".join(argv[:2]), r.stderr or r.stdout))
    return r


def script(name, *args):
    return [os.path.join(SCRIPTS, name)] + list(args)


def unapprove_round4(dest_root, verbose=True):
    """Re-select round 4 with nobody named as the approver.

    The committed record was approved on a laptop at a moment in time and
    carries that moment inside the hash. What ships is the record the
    optimizer wrote before anyone signed it, which is reproducible anywhere,
    and the assertion below is that signing it was the only difference.
    """
    root = os.path.join(dest_root, "projects", DEMO)
    committed = schema.read_json(os.path.join(REPO, "projects", DEMO, "batches",
                                              "batch_004.json"))
    # Only selection is re-run. pool_004 records the designs.json hash as it
    # stood *before* round 4's designs existed -- selection is what adds them --
    # so regenerating the pool now would rewrite a true record of the past with
    # a hash taken in the present.
    run(script("select_batch.py", "--project", root, "--round", "4"))
    fresh = schema.read_json(os.path.join(root, "batches", "batch_004.json"))

    differ = sorted(k for k in set(fresh) | set(committed) if fresh.get(k) != committed.get(k))
    if differ != ["approval", "hash"]:
        raise SystemExit("re-selecting round 4 changed more than the approval: %s" % differ)
    if verbose:
        print("batch_004      %s unapproved  (committed %s, approved by %s)"
              % (schema.short_hash(fresh["hash"]), schema.short_hash(committed["hash"]),
                 committed["approval"]["by"]))
    return fresh


# The snapshot points at the batch that produced it, so a batch that lost its
# approval stamp necessarily changes these two fields and nothing else.
SNAPSHOT_EXPECTED_DIFF = ["hash", "inputs"]


def requirements():
    """What this project needs before a single round can run.

    Gap 109 of the phase-5b audit, rendered rather than argued: the plugin
    manifest already declares the interpreter, both servers and the skill, and
    a loader satisfies all three. What no manifest can declare is the sandbox
    grant -- in Claude Science that became a hand-written `[sandbox]` key in a
    file the published configuration reference does not mention, plus a
    restart. Every row below is read out of the repository's own manifests or
    its own connector modules; only the `satisfied_by` column is ours.
    """
    plugin = schema.read_json(os.path.join(REPO, ".claude-plugin", "plugin.json"))
    sys.path.insert(0, os.path.join(REPO, "connectors"))
    import lims as lims_mod                                      # noqa: PLC0415
    tools = {"registry": [t for t, _ in lims_mod.TOOLS]}
    src = open(os.path.join(REPO, "connectors", "bioprovider_server.py"),
               encoding="utf-8").read()
    tools["bioprovider"] = [line.split('"')[1] for line in src.split("TOOLS = [")[1]
                            .split("]")[0].strip().splitlines() if '("' in line]
    withheld = [w.strip().strip('"') for w in
                open(os.path.join(REPO, "connectors", "registry_server.py"), encoding="utf-8")
                .read().split("WITHHELD = [")[1].split("]")[0].split(",")]

    servers = []
    for name, spec in plugin["mcpServers"].items():
        servers.append({
            "name": name, "transport": spec["type"],
            "command": spec["command"], "args": spec["args"],
            "tools": tools.get(name, []),
            "withheld": withheld if name == "registry" else [],
        })
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "kind": "project_requirements",
        "plugin": {"name": plugin["name"], "version": plugin["version"]},
        "needs": [
            {"what": "an interpreter", "value": plugin["mcpServers"]["registry"]["command"],
             "declared_in": ".claude-plugin/plugin.json",
             "satisfied_by": "the loader, in Claude Code",
             "in_the_host": "refused; the sandbox will not exec a binary under $HOME, and "
                            "the host supplies its own bare `python` instead"},
            {"what": "two stdio connectors", "value": "registry, bioprovider",
             "declared_in": ".claude-plugin/plugin.json",
             "satisfied_by": "the loader, in Claude Code",
             "in_the_host": "one dialog each, a whole command line in a single field"},
            {"what": "the skill", "value": "skills/adaptive-optimization",
             "declared_in": ".claude-plugin/marketplace.json",
             "satisfied_by": "the loader, in Claude Code",
             "in_the_host": "imported from GitHub, with its commit recorded"},
            {"what": "read access to the code and the project", "value": "<repository root>",
             "declared_in": "nothing declares this",
             "satisfied_by": "the working directory, in Claude Code",
             "in_the_host": "a hand-written [sandbox] user_read_paths in "
                            "~/.claude-science/config.toml, and a restart"},
            {"what": "write access, and only here", "value": "lims_store/",
             "declared_in": "nothing declares this",
             "satisfied_by": "the working directory, in Claude Code",
             "in_the_host": "user_write_paths, beside it, in the same undocumented block"},
        ],
        "servers": servers,
        "note": ("The first three rows a manifest declares and a loader satisfies. The "
                 "last two no manifest can express, which is the finding: the host has "
                 "every primitive needed -- sandbox grants, per-tool approval, a "
                 "local-command transport -- and no way for a connector to say what it "
                 "requires."),
    }


def verify_replay(dest_root, verbose=True):
    """Replay round 4 forward and require the committed snapshot back.

    This is the derivation's proof. Everything above removes things; this puts
    them back by running the real registry and the real import script, and
    compares field by field against what the repository holds.
    """
    committed = schema.read_json(os.path.join(REPO, "projects", DEMO, "evidence",
                                              "snapshot_004.json"))
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, DEMO)
        shutil.copytree(os.path.join(dest_root, "projects", DEMO), root)
        store = os.path.join(tmp, "store.json")
        shutil.copyfile(os.path.join(dest_root, "lims_store", "%s.json" % DEMO), store)
        # The committed snapshot records the export's filename, so the replay
        # pulls to the same name and imports under the same policy the
        # scheduler used when the round was first run.
        csv_path = os.path.join(tmp, "%s_round4.csv" % DEMO)

        lims = os.path.join(REPO, "lims.py")
        run([lims, "submit", "--project", root, "--round", "4", "--store", store])
        run([lims, "pull", "--project", root, "--round", "R4", "--out", csv_path,
             "--store", store])
        run(script("import_round.py", "--project", root, "--round", "4",
                   "--results", csv_path, "--offset", "if-clear",
                   "--authority", "bridge_policy:run_rounds --offset if-clear"))
        run(script("evaluate_prior.py", "--project", root, "--round", "4"))

        again = schema.read_json(os.path.join(root, "evidence", "snapshot_004.json"))
        differ = sorted(k for k in set(again) | set(committed)
                        if again.get(k) != committed.get(k))
        if verbose:
            print("replay         round 4 re-measured: %d rows, anomaly %+.6f, bridge %+.6f"
                  % (again["source"]["rows"], again["anomaly"]["mean_signed_residual"],
                     again["frame"]["offset_estimate"]["offset"]))
        if differ != SNAPSHOT_EXPECTED_DIFF:
            raise SystemExit("the rewound state does not replay to the committed round 4; "
                             "fields differing: %s" % differ)
        if again["inputs"]["designs"] != committed["inputs"]["designs"]:
            raise SystemExit("re-submitting round 4 did not restore designs.json")
        return again


def write_skill_module():
    """SKILL.md as an ES module: the text, verbatim, and its sha256."""
    src = os.path.join(REPO, SKILL)
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    dst = os.path.join(REPO, SKILL_MODULE)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write("// Generated by web/bundle.py from %s. Do not edit; edit the skill.\n"
                 "// The model in the centre column is given this text as its system\n"
                 "// prompt, so the browser, Claude Code and Claude Science are driven by\n"
                 "// one file. check.py requires the string below to be that file.\n"
                 "export const SKILL_PATH = %s;\n"
                 "export const SKILL_SHA256 = %s;\n"
                 "export const SKILL_MD = %s;\n"
                 % (SKILL, json.dumps(SKILL), json.dumps(sha(src)),
                    json.dumps(text, ensure_ascii=False)))
    return dst


def check_skill_module():
    """Is the module the skill as it stands now?"""
    dst = os.path.join(REPO, SKILL_MODULE)
    if not os.path.exists(dst):
        return False, "no %s" % SKILL_MODULE
    with open(dst, encoding="utf-8") as fh:
        body = fh.read()
    marker = "export const SKILL_MD = "
    if marker not in body:
        return False, "%s carries no SKILL_MD" % SKILL_MODULE
    text = json.loads(body.split(marker, 1)[1].rstrip().rstrip(";"))
    with open(os.path.join(REPO, SKILL), encoding="utf-8") as fh:
        same = fh.read() == text
    return same, "" if same else "%s has moved on from %s" % (SKILL, SKILL_MODULE)


def build(verbose=True):
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    for rel in CODE:
        copy(rel, OUT)
    driver_dst = os.path.join(OUT, "wb_driver.py")
    shutil.copyfile(os.path.join(REPO, DRIVER), driver_dst)
    write_skill_module()

    _, minted = rewind_project(OUT)
    rewind_store(OUT, minted)
    unapprove_round4(OUT, verbose=verbose)
    os.makedirs(os.path.join(OUT, "reference"), exist_ok=True)
    schema.write_json(os.path.join(OUT, "reference", "decision_004.proposal.json"),
                      proposal_payload())
    shutil.copyfile(os.path.join(REPO, "projects", DEMO, "decisions", "decision_004.json"),
                    os.path.join(OUT, "reference", "decision_004.json"))
    shutil.copyfile(os.path.join(REPO, "projects", DEMO, "decisions", "decision_002.json"),
                    os.path.join(OUT, "reference", "decision_002.json"))
    schema.write_json(os.path.join(OUT, "reference", "requirements.json"), requirements())

    verify_replay(OUT, verbose=verbose)

    code = [{"path": rel, "sha256": sha(os.path.join(OUT, rel)), "verbatim": True}
            for rel in CODE]
    code.append({"path": "wb_driver.py", "sha256": sha(driver_dst), "verbatim": False,
                 "source": DRIVER})
    state, reference = [], []
    for group, prefix in (("state", "projects"), ("state", "lims_store"),
                          ("reference", "reference")):
        for base, _dirs, files in os.walk(os.path.join(OUT, prefix)):
            for name in sorted(files):
                full = os.path.join(base, name)
                rel = os.path.relpath(full, OUT).replace(os.sep, "/")
                entry = {"path": rel, "sha256": sha(full)}
                (state if group == "state" else reference).append(entry)
    state.sort(key=lambda e: e["path"])

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True)
    manifest = {
        "schema_version": schema.SCHEMA_VERSION,
        "kind": "browser_bundle",
        "note": ("code is copied byte for byte from the repository and laid out in the "
                 "same shape, so Pyodide imports the same modules the CLI imports. "
                 "state is the committed project rewound to before round 4 was "
                 "submitted. reference is read for replay and never executed"),
        "project": DEMO,
        "mount": "/workbench",
        "commit": (head.stdout or "").strip() or None,
        "code": code,
        "state": state,
        "reference": reference,
    }
    manifest = schema.stamp(manifest)
    schema.write_json(os.path.join(OUT, "manifest.json"), manifest)

    if verbose:
        total = sum(os.path.getsize(os.path.join(b, f))
                    for b, _d, fs in os.walk(OUT) for f in fs)
        print("code           %d files copied verbatim" % len(CODE))
        print("state          %d files, project rewound to round 4 pending" % len(state))
        print("reference      %d files, replayed and never executed" % len(reference))
        print("bundle         %.0f KB at web/public/workbench" % (total / 1024.0))
        print("manifest       %s" % schema.short_hash(manifest["hash"]))
    return manifest


def check():
    """Is the written bundle the one this repository would write now?"""
    path = os.path.join(OUT, "manifest.json")
    if not os.path.exists(path):
        return False, "no bundle at web/public/workbench"
    current = schema.read_json(path)
    drifted = []
    skill_ok, why = check_skill_module()
    if not skill_ok:
        drifted.append(why)
    for entry in current["code"]:
        src = os.path.join(REPO, entry.get("source") or entry["path"])
        dst = os.path.join(OUT, entry["path"])
        if not os.path.exists(dst) or sha(dst) != entry["sha256"]:
            drifted.append(entry["path"] + " (bundle edited)")
        elif not os.path.exists(src) or sha(src) != entry["sha256"]:
            drifted.append(entry["path"] + " (source moved on)")
    for entry in current["state"] + current["reference"]:
        dst = os.path.join(OUT, entry["path"])
        if not os.path.exists(dst) or sha(dst) != entry["sha256"]:
            drifted.append(entry["path"])
    return (not drifted), ", ".join(drifted[:4]) + ("" if len(drifted) <= 4
                                                    else " and %d more" % (len(drifted) - 4))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="verify the written bundle matches the repository")
    args = ap.parse_args(argv)
    if args.check:
        ok, why = check()
        print("bundle is current" if ok else "bundle has drifted: %s" % why)
        return 0 if ok else 1
    build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
