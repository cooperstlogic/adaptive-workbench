#!/usr/bin/env python3
"""Enumerate the candidate pool and enforce every declared constraint.

    python generate_candidates.py --project projects/demo-trastuzumab --round 2

Reads objectives.json, writes candidates/pool_NNN.json.

Constraints declared in the template are enforced here, in code, before any
optimization runs -- they are not suggested to a model. The record says how
many candidates were removed and why, because a filter that silently drops
four thousand molecules is a claim about chemistry and has to be inspectable.

The pool itself is not stored. Enumeration is deterministic, so the record
carries a content hash over the ordered pool and every later artifact indexes
into that order. Storing the hash costs a line; storing the pool costs most of
a megabyte per round.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from core import project, schema  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="path to the project directory")
    ap.add_argument("--round", type=int, required=True)
    args = ap.parse_args(argv)

    state = project.load(args.project)
    obj = state["objectives"]
    schema.assert_unit(obj["unit"], "objectives")

    kept, removed, summary = project.feasible_pool(state)
    region = obj["editable_region"]

    record = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "round": int(args.round),
        "unit": obj["unit"],
        "editable_region": list(region),
        "max_mutations": obj["constraints"]["max_mutations"],
        "enumerated": len(kept) + len(removed),
        "feasible": len(kept),
        "removed": len(removed),
        "removed_by_reason": summary,
        "constraints_enforced": obj["constraints"],
        "computed_thresholds": [
            {"name": o["name"], "direction": o["direction"], "threshold": o.get("threshold")}
            for o in obj["objectives"] if o.get("source") == "computed"
        ],
        "pool_fingerprint": project.pool_fingerprint(kept),
        "pool_order": ("core.candidates.enumerate_variants then constraint_report; "
                       "deterministic, so the pool is hashed rather than stored"),
    }, inputs={"objectives": obj["hash"], "designs": state["designs"]["hash"]})

    path = project.artifact_path(state, "candidates", args.round)
    schema.write_json(path, record)
    project.link_round(state, args.round,
                       pool=project.artifact_ref(state["paths"]["root"], path, record))

    print("round           %d" % args.round)
    print("editable region %s -> %s" % (region, state["designs"]["parent"][region[0]:region[1]]))
    print("enumerated      %d under a budget of %d mutations"
          % (record["enumerated"], record["max_mutations"]))
    print("feasible        %d  (removed %d: %s)" % (len(kept), len(removed), summary))
    print("pool            %s" % schema.short_hash(record["pool_fingerprint"]))
    print("wrote           %s" % os.path.relpath(path, args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
