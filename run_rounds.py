#!/usr/bin/env python3
"""Drive the round loop through the CLI scripts, one subprocess at a time.

    python run_rounds.py --project projects/demo-trastuzumab --rounds 6

This is deliberately a dumb scheduler. It calls the five pipeline scripts in
order, shells out to the mock LIMS between selection and import, and prints
every command it runs so that the pipeline is visible rather than implied.

That is the argument, not a shortcut. Import, fit, generate, select, repeat is
a pipeline, and a pipeline needs no agent -- a scheduler runs the same steps
whatever comes back. What a scheduler cannot do is decide what an ambiguous
round means, which is why this script **stops** when a round is flagged and
unruled. Everything up to that stop is automation. The stop is where the
judgment is, and it is the part the skill and the decision record exist for.

    --ignore-flags   carry on through a flagged round without a ruling, which
                     pools its raw frame as returned.

    --offset         what authorizes moving a round into the project frame.
                     ``if-clear`` is the scheduler's own policy and the
                     default: normalize a round that did not flag from its
                     bridging controls, which is routine, and leave a flagged
                     round raw for a human to rule on. ``never`` corrects
                     nothing, which with --ignore-flags is exactly the
                     naive-pooling arm of the proof chart. ``always``
                     corrects every round, which with --ignore-flags is
                     exactly the corrected guided arm. Both of those exist so
                     the CLI path can be checked against the evaluator: the
                     same six batches, well for well.
"""

import argparse
import os
import subprocess
import sys

from core import project, schema

REPO = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(REPO, "skills", "adaptive-optimization", "scripts")
PY = sys.executable


def run(argv, echo=True):
    if echo:
        shown = [os.path.relpath(a, REPO) if a.startswith(REPO) else a for a in argv[1:]]
        shown = ["'%s'" % a if " " in a else a for a in shown]
        print("\n$ python %s" % " ".join(shown), flush=True)
    proc = subprocess.run([PY] + argv[1:], cwd=REPO, capture_output=True, text=True)
    if proc.stdout:
        print("".join("  " + line + "\n" for line in proc.stdout.rstrip("\n").split("\n")),
              end="", flush=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr)
        raise SystemExit("step failed: %s" % " ".join(argv[1:]))
    if proc.stderr.strip():
        print("".join("  ! " + line + "\n" for line in proc.stderr.rstrip("\n").split("\n")),
              end="", flush=True)
    return proc


def script(name, *args):
    return [PY, os.path.join(SCRIPTS, name)] + list(args)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.path.join(REPO, "projects", "demo-trastuzumab"))
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--ignore-flags", action="store_true")
    ap.add_argument("--offset", choices=("never", "if-clear", "always"), default="if-clear")
    ap.add_argument("--approved-by", default=None)
    ap.add_argument("--run-seed", type=int, default=0)
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--lims-store", default=None,
                    help="where the mock LIMS keeps its records; defaults to "
                         "lims_store/<project>.json")
    args = ap.parse_args(argv)

    proj = os.path.abspath(args.project)
    results_dir = args.results_dir or os.path.join(REPO, "lims_store", "exports")
    os.makedirs(results_dir, exist_ok=True)

    for r in range(args.start, args.rounds + 1):
        print("\n" + "=" * 72)
        print("ROUND %d" % r)
        print("=" * 72)

        run(script("generate_candidates.py", "--project", proj, "--round", str(r)))

        select = ["--project", proj, "--round", str(r)]
        if args.approved_by:
            select += ["--approved-by", args.approved_by]
        run(script("select_batch.py", *select))

        store = ["--store", args.lims_store] if args.lims_store else []
        run([PY, os.path.join(REPO, "lims.py"), "submit", "--project", proj,
             "--round", str(r), "--run-seed", str(args.run_seed)] + store)
        csv_path = os.path.join(results_dir, "%s_round%d.csv"
                                % (os.path.basename(proj), r))
        run([PY, os.path.join(REPO, "lims.py"), "pull", "--project", proj,
             "--round", "R%d" % r, "--out", csv_path] + store)

        imp = ["--project", proj, "--round", str(r), "--results", csv_path,
               "--offset", args.offset]
        if args.offset != "never":
            imp += ["--authority", "bridge_policy:run_rounds --offset %s" % args.offset]
        run(script("import_round.py", *imp))
        run(script("evaluate_prior.py", "--project", proj, "--round", str(r)))

        state = project.load(proj)
        snap = project.read_artifact(state, "evidence", r)
        if snap["flagged"] and snap["frame"]["authority"] == "unruled":
            print("\n" + "-" * 72)
            print("ROUND %d IS FLAGGED AND UNRULED" % r)
            print("-" * 72)
            print("  %s" % snap["anomaly"]["statistic"])
            print("  mean signed residual %+.3f %s over %d fresh designs, trigger %.2f"
                  % (snap["anomaly"]["mean_signed_residual"], snap["unit"],
                     snap["anomaly"]["n_compared"], snap["anomaly"]["trigger_abs_pkd"]))
            print("  assay version %s, %s"
                  % (snap["assay_version"],
                     "not previously characterized" if snap["anomaly"]["known_version_offset"]
                     is None else "offset already known"))
            print("  bridge estimate %+.3f %s over %d shared designs"
                  % (snap["frame"]["offset_estimate"]["offset"], snap["unit"],
                     snap["frame"]["offset_estimate"]["n"]))
            if not args.ignore_flags:
                print("\n  A scheduler cannot decide what this means. Diagnose the round and")
                print("  record a ruling, then re-import with --apply-offset --authority, or")
                print("  re-run with --ignore-flags to pool the raw frame as returned.")
                print("\nstopped at round %d of %d" % (r, args.rounds))
                return 3
            print("\n  --ignore-flags: pooling the raw frame as returned, which is the")
            print("  naive-pooling arm of the proof chart.")

        run(script("fit_surrogates.py", "--project", proj, "--round", str(r)))

    state = project.load(proj)
    records = project.measurement_records(state)
    from core import reconcile
    pooled = reconcile.pool(records)
    best = max(pooled.values(), key=lambda v: v["value"])
    by_sequence = {d["sequence"]: d["design_id"] for d in state["designs"]["designs"]}
    print("\n" + "=" * 72)
    print("ran rounds %d-%d through the CLI scripts" % (args.start, args.rounds))
    print("designs         %d in designs.json, %d measured"
          % (len(state["designs"]["designs"]), len(pooled)))
    print("best observed   %.3f %s  (design %s, %d measurement%s)"
          % (best["value"], state["objectives"]["unit"], by_sequence[best["sequence"]],
             best["n_measurements"], "" if best["n_measurements"] == 1 else "s"))
    flagged = [r["round"] for r in state["rounds"]["rounds"] if r.get("flagged")]
    print("flagged rounds  %s" % (flagged or "none"))
    print("rounds.json     %d entries, %s" % (len(state["rounds"]["rounds"]),
                                              schema.short_hash(state["rounds"]["hash"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
