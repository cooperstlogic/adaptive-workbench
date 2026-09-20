#!/usr/bin/env python3
"""Fit every registered recipe, cross-validate, and pick a winner.

    python fit_surrogates.py --project projects/demo-trastuzumab --round 2

Reads every snapshot the project holds, writes models/run_NNN.json.

Two recipes, and only two: the registry is closed. ``ridge_onehot`` is ridge
regression on the one-hot block read as Bayesian linear regression, so the
predictive variance is analytic. ``gp_pca64`` is an exact Gaussian process
with an RBF kernel on the first sixty-four principal components of the active
feature block. Both are under fifty lines of numpy.

The winner is the lowest held-out negative log predictive density, not the
lowest error. A recipe that is accurate but overconfident loses to one that
knows what it does not know, because knowing what it does not know is the
property batch selection actually consumes.

Censored wells enter the fit at the detection limit, carrying a flag. That
biases them slightly upward and is the boring choice; a Tobit likelihood is
the correct one and is not worth the hour. The count is recorded on the run
and surfaced in the batch table.

The run stores one prediction per member of the candidate pool, in the pool's
hashed order, which is what the next round's selection consumes.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from core import project, reconcile, schema, surrogate  # noqa: E402

PREDICTION_DECIMALS = 6


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--round", type=int, required=True)
    args = ap.parse_args(argv)

    state = project.load(args.project)
    obj = state["objectives"]
    region = obj["editable_region"]

    pool_rec = project.read_artifact(state, "candidates", args.round)
    if pool_rec is None:
        print("no candidate pool for round %d; run generate_candidates.py first" % args.round,
              file=sys.stderr)
        return 2
    kept, _, _ = project.feasible_pool(state)
    fingerprint = project.pool_fingerprint(kept)
    if fingerprint != pool_rec["pool_fingerprint"]:
        print("the feasible pool no longer hashes to what pool_%03d.json recorded"
              % args.round, file=sys.stderr)
        return 2

    snaps = project.snapshots(state, through=args.round)
    if not snaps:
        print("no snapshots through round %d; run import_round.py first" % args.round,
              file=sys.stderr)
        return 2
    for recipe in obj["model_recipes"]:
        if recipe not in surrogate.RECIPES:
            print("recipe %r is not in the registry %s" % (recipe, list(surrogate.RECIPES)),
                  file=sys.stderr)
            return 2

    pooled = reconcile.pool(project.measurement_records(state, through=args.round))
    observations = [{"sequence": s, "value": v["value"], "censored": v["censored"]}
                    for s, v in pooled.items()]

    features = surrogate.Features(kept, region)
    run = surrogate.fit_surrogates(features, observations,
                                   recipes=tuple(obj["model_recipes"]))
    summary = surrogate.run_summary(run)

    # A flagged round is settled by a ruling and not by a frame move: the
    # commonest correct ruling -- refit and touch nothing -- changes no
    # measurement, so the snapshot it leaves behind still says its frame was
    # never moved. Whether a human has ruled is read from the decision record.
    unruled = project.unruled_flagged_rounds(state, through=args.round)

    record = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "round": int(args.round),
        "unit": obj["unit"],
        "feature_block": summary["feature_block"],
        "n_components": summary["n_components"],
        "n_observations": summary["n_observations"],
        "n_censored": summary["n_censored"],
        "censored_rule": "entered at the detection limit with a flag; biases them slightly "
                         "upward, and a Tobit likelihood is the correct alternative",
        "rounds_included": [int(s["round"]) for s in snaps],
        "unruled_flagged_rounds": unruled,
        "pooling_note": ("measurements are pooled across %d rounds and %d assay versions; "
                         "rounds %s are flagged and have no ruling, so their raw frame "
                         "is being pooled as returned"
                         % (len(snaps), len({s["assay_version"] for s in snaps}), unruled)
                         if unruled else
                         "measurements are pooled across %d rounds; every flagged round has "
                         "a ruling" % len(snaps)),
        "recipes": summary["recipes"],
        "registry": list(surrogate.RECIPES),
        "winner": summary["winner"],
        "selection_rule": summary["selection_rule"],
        "incumbent": summary["incumbent"],
        "pool_fingerprint": fingerprint,
        "pool_size": len(kept),
        "prediction_decimals": PREDICTION_DECIMALS,
        "pool_mean": [round(float(v), PREDICTION_DECIMALS) for v in run["pool_mean"]],
        "pool_sd": [round(float(v), PREDICTION_DECIMALS) for v in run["pool_sd"]],
    }, inputs={
        "objectives": obj["hash"], "pool": pool_rec["hash"],
        "snapshots": schema.content_hash([s["hash"] for s in snaps]),
    })

    path = project.artifact_path(state, "models", args.round)
    schema.write_json(path, record)
    project.link_round(state, args.round,
                       model=project.artifact_ref(state["paths"]["root"], path, record))

    print("round           %d" % args.round)
    print("trained on      %d designs from rounds %s, %d censored"
          % (record["n_observations"], record["rounds_included"], record["n_censored"]))
    print("feature block   %s, %d principal components" % (record["feature_block"],
                                                           record["n_components"]))
    print("%-15s %7s %7s %7s %7s" % ("recipe", "rmse", "r2", "cov80", "nlpd"))
    for name in obj["model_recipes"]:
        cv = record["recipes"][name]
        print("%-15s %7.3f %7.3f %7.2f %7.3f%s"
              % (name, cv["rmse"], cv["r2"], cv["coverage_80"], cv["nlpd"],
                 "   <- winner" if name == record["winner"] else ""))
    print("selection       %s" % record["selection_rule"])
    if unruled:
        print("pooling         rounds %s are flagged with no ruling; their raw frame is "
              "pooled as returned" % unruled)
    print("predictions     %d pool members, written at %d decimals"
          % (record["pool_size"], PREDICTION_DECIMALS))
    print("wrote           %s" % os.path.relpath(path, args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
