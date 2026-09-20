#!/usr/bin/env python3
"""Run one library diagnostic against a round and print what it returns.

    python run_diagnostic.py --project projects/demo-trastuzumab --round 4 \
        --test offset_from_controls

    python run_diagnostic.py --project projects/demo-trastuzumab --round 4 \
        --test calibration_by_region --offset bridge

**It writes nothing.** Reading a round is not a decision, and nothing about a
project changes because somebody looked at it. The writing happens once, in
``record_decision.py``, when a diagnosis is committed to.

The test must be one the template permits. That list is in `objectives.json`
and it is checked here rather than trusted: an agent that could name a sixth
test could put a number in a decision record that no reviewer can reproduce.
The tolerances come from the template too, so two people reading the same
round get the same answer.

Output is JSON on stdout and a human summary on stderr, so it pipes into `jq`
and still reads in a terminal.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from core import diagnostics, project, schema  # noqa: E402


def load_round(state, round_id):
    """-> (snapshot, batch, prior model run). All three or a reason why not."""
    snap = project.read_artifact(state, "evidence", round_id)
    batch = project.read_artifact(state, "batches", round_id)
    if snap is None:
        return None, None, None, "round %d has no snapshot; import it first" % round_id
    if batch is None:
        return None, None, None, "round %d has no batch, so nothing was predicted" % round_id
    return snap, batch, project.read_artifact(state, "models", round_id - 1), None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--test", required=True, choices=list(diagnostics.TESTS))
    ap.add_argument("--by", choices=list(diagnostics.MUTATION_CLASS_BY), default="position",
                    help="residual_by_mutation_class: what a class is (default: position)")
    ap.add_argument("--offset", choices=list(diagnostics.OFFSET_SOURCES), default="none",
                    help="calibration_by_region: score the counterfactual in which this "
                         "round's measurements are moved by the named estimate "
                         "(default: none)")
    ap.add_argument("--scope", choices=("all", "fresh"), default="all",
                    help="every design the round predicted and measured, or only the fresh "
                         "ones the anomaly flag was computed over (default: all)")
    args = ap.parse_args(argv)

    state = project.load(args.project)
    obj = state["objectives"]
    if args.test not in obj["diagnostics"]:
        print("%r is not in this project's permitted diagnostics: %s"
              % (args.test, ", ".join(obj["diagnostics"])), file=sys.stderr)
        return 2

    snap, batch, prior_run, problem = load_round(state, args.round)
    if problem:
        print(problem, file=sys.stderr)
        return 2

    call = {"test": args.test, "scope": args.scope}
    if args.test == "residual_by_mutation_class":
        call["by"] = args.by
    if args.test == "calibration_by_region":
        call["offset"] = args.offset

    result = diagnostics.run(args.test, snap, batch, project.designs_by_id(state),
                             policy=obj.get("diagnostics_policy"), args=call)
    record = {
        "test": args.test,
        "round": int(args.round),
        "project": state["project"]["id"],
        "args": call,
        "policy": {k: v for k, v in (obj.get("diagnostics_policy") or {}).items()
                   if k in diagnostics.DEFAULT_POLICY},
        "result": result,
        "inputs": {
            "snapshot": snap["hash"],
            "batch": batch["hash"],
            "model_run": None if prior_run is None else prior_run["hash"],
        },
        "source": "core.diagnostics.%s" % args.test,
        "note": "read-only; this call wrote nothing",
    }
    print(json.dumps(schema.canonicalize(record), indent=2, sort_keys=True))

    say = lambda line: print(line, file=sys.stderr)  # noqa: E731
    say("%s  round %d  %s" % (args.test, args.round, state["project"]["id"]))
    say("scored          %d designs (%s)" % (result["n_scored"], result["scored_excludes"]))
    say("frame           offset applied %+.3f, authority %s"
        % (result["frame"]["offset_applied"], result["frame"]["authority"]))
    say(result["note"])
    say("inputs          snapshot %s, batch %s"
        % (schema.short_hash(snap["hash"]), schema.short_hash(batch["hash"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
