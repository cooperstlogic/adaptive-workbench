#!/usr/bin/env python3
"""Score the last round's predictions against what the lab returned.

    python evaluate_prior.py --project projects/demo-trastuzumab --round 2

Reads batches/batch_NNN.json and evidence/snapshot_NNN.json, writes
batches/batch_NNN.eval.json.

It scores predictions for the designs that were **approved**, not the ones
that were recommended. If a scientist removed four designs, the model is not
credited or blamed for them, and that distinction is the reason the batch
record keeps the two lists apart.

Three things come out of it. Whether the model's eighty percent interval
actually covered eighty percent of what came back, which is the number that
tells you whether to trust the next batch. How far coverage moved from the
held-out estimate the model reported at fit time, because a model that
calibrates well in cross-validation and badly on the next real round is
telling you the rounds are not exchangeable. And realized improvement over
the incumbent the batch was selected against.

**On baselines.** The comparison against random selection is a property of
the evaluator, not of a single project: measuring it inside a live campaign
would mean spending wells on designs nobody wanted. What this script can
compare against honestly is the project's own round-1 batch -- the template's
scan, the only batch chosen without a model -- and that is what it reports.
The random-arm curve lives in campaign.json and is labelled as coming from
simulate_campaign.py.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import numpy as np  # noqa: E402

from core import project, schema, surrogate  # noqa: E402


def stats(residuals):
    r = np.asarray(residuals, dtype=np.float64)
    if r.size == 0:
        return {"n": 0, "rmse": None, "mean_signed": None, "mae": None}
    return {"n": int(r.size), "rmse": float(np.sqrt((r ** 2).mean())),
            "mean_signed": float(r.mean()), "mae": float(np.abs(r).mean())}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--round", type=int, required=True)
    args = ap.parse_args(argv)

    state = project.load(args.project)
    obj = state["objectives"]
    batch = project.read_artifact(state, "batches", args.round)
    snap = project.read_artifact(state, "evidence", args.round)
    if batch is None or snap is None:
        print("round %d needs both a batch and a snapshot" % args.round, file=sys.stderr)
        return 2

    prior_run = project.read_artifact(state, "models", args.round - 1)
    slot_of = {s["design_id"]: s for s in batch["slots"]}
    got = {m["design_id"]: m for m in snap["measurements"]}
    approved = [d for d in batch["approved"] if d in got]

    interval = float(obj["anomaly_flag"].get("interval", 0.80))
    z = surrogate.z_for_central(interval)

    scored, by_slot = [], {}
    for did in approved:
        slot, m = slot_of[did], got[did]
        if m["value"] is None or m["censored"] or slot.get("pred_mean") is None:
            continue
        resid = float(m["value"]) - float(slot["pred_mean"])
        inside = abs(resid) <= z * float(slot["pred_sd"])
        rec = {"design_id": did, "slot": slot["slot"], "observed": float(m["value"]),
               "pred_mean": float(slot["pred_mean"]), "pred_sd": float(slot["pred_sd"]),
               "residual": resid, "inside_interval": bool(inside),
               "extrapolation": bool(slot.get("extrapolation"))}
        scored.append(rec)
        by_slot.setdefault(slot["slot"], []).append(rec)

    calibration = None
    if scored:
        held_out = (prior_run or {}).get("recipes", {}).get(
            (prior_run or {}).get("winner", ""), {}).get("coverage_80")
        realized = float(np.mean([s["inside_interval"] for s in scored]))
        calibration = {
            "interval": interval,
            "nominal_coverage": interval,
            "realized_coverage": realized,
            "held_out_coverage_at_fit": held_out,
            "drift_from_held_out": None if held_out is None else realized - float(held_out),
            "residuals": stats([s["residual"] for s in scored]),
            "by_slot": {k: dict(stats([r["residual"] for r in v]),
                                coverage=float(np.mean([r["inside_interval"] for r in v])))
                        for k, v in sorted(by_slot.items())},
            "extrapolating": {
                "n": sum(1 for s in scored if s["extrapolation"]),
                "coverage": (float(np.mean([s["inside_interval"] for s in scored
                                            if s["extrapolation"]]))
                             if any(s["extrapolation"] for s in scored) else None),
            },
            "frame_note": ("residuals are against the snapshot as recorded, in the %s frame "
                           "under authority %r; a flagged round that has not been ruled on "
                           "carries its run offset into these numbers, which is what the "
                           "anomaly flag saw"
                           % ("corrected" if snap["frame"]["offset_applied"] else "raw assay",
                              snap["frame"]["authority"])),
        }

    values = [m["value"] for m in snap["measurements"]
              if m["value"] is not None and not m["censored"]]
    fresh = [m["value"] for m in snap["measurements"]
             if m["fresh"] and m["value"] is not None and not m["censored"]]
    base = None if args.round == 1 else project.read_artifact(state, "evidence", 1)
    base_values = [] if base is None else [
        m["value"] for m in base["measurements"]
        if m["value"] is not None and not m["censored"]]

    improvement = {
        "incumbent_at_selection": batch["incumbent"],
        "best_this_round": max(values) if values else None,
        "best_fresh_this_round": max(fresh) if fresh else None,
        "gain_over_incumbent": (None if batch["incumbent"] is None or not values
                                else max(values) - float(batch["incumbent"])),
        "mean_fresh": float(np.mean(fresh)) if fresh else None,
    }
    baseline = {
        "kind": "unguided_round_1",
        "note": ("round 1 is the only batch in this project chosen without a model. The "
                 "random-selection arm is an evaluator construct and lives in "
                 "campaign.json, not here."
                 if base else
                 "this round is the baseline; there is nothing un-guided to compare it to"),
        "n": len(base_values),
        "mean": float(np.mean(base_values)) if base_values else None,
        "best": max(base_values) if base_values else None,
        "gain_in_mean": (float(np.mean(fresh)) - float(np.mean(base_values))
                         if fresh and base_values else None),
        "gain_in_best": (max(values) - max(base_values)) if values and base_values else None,
    }

    record = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "round": int(args.round),
        "unit": obj["unit"],
        "model_run": None if prior_run is None else prior_run["round"],
        "model_winner": (prior_run or {}).get("winner"),
        "n_recommended": len(batch["recommended"]),
        "n_approved": len(batch["approved"]),
        "n_overridden": len(batch["overrides"]),
        "overrides_note": ("predictions are scored for approved designs only; the model is "
                           "neither credited nor blamed for designs a scientist removed"),
        "n_returned": len(got),
        "n_scored": len(scored),
        "scored_excludes": "construct failures, censored wells, and round-1 designs with "
                           "no prior model",
        "calibration": calibration,
        "improvement": improvement,
        "baseline": baseline,
        "per_design": scored,
    }, inputs={"batch": batch["hash"], "snapshot": snap["hash"],
               "model_run": None if prior_run is None else prior_run["hash"]})

    path = project.artifact_path(state, "batches", args.round, suffix=".eval")
    schema.write_json(path, record)
    project.link_round(state, args.round,
                       evaluation=project.artifact_ref(state["paths"]["root"], path, record))

    print("round           %d" % args.round)
    print("approved        %d of %d recommended, %d overridden"
          % (record["n_approved"], record["n_recommended"], record["n_overridden"]))
    if calibration is None:
        print("calibration     not scored: round %d carried no model predictions" % args.round)
    else:
        c = calibration
        print("scored          %d approved designs against run %03d (%s)"
              % (len(scored), prior_run["round"], record["model_winner"]))
        print("coverage        %.2f realized against %.2f nominal%s"
              % (c["realized_coverage"], c["nominal_coverage"],
                 "" if c["drift_from_held_out"] is None else
                 ", %+.2f from the %.2f held out at fit time"
                 % (c["drift_from_held_out"], c["held_out_coverage_at_fit"])))
        print("residuals       rmse %.3f, mean signed %+.3f %s over %d designs"
              % (c["residuals"]["rmse"], c["residuals"]["mean_signed"], obj["unit"],
                 c["residuals"]["n"]))
        for kind, s in c["by_slot"].items():
            print("  %-12s  n %2d  mean signed %+.3f  coverage %.2f"
                  % (kind, s["n"], s["mean_signed"], s["coverage"]))
    if improvement["best_this_round"] is not None:
        print("best this round %.3f %s%s"
              % (improvement["best_this_round"], obj["unit"],
                 "" if improvement["gain_over_incumbent"] is None else
                 "  (%+.3f on the incumbent it was selected against)"
                 % improvement["gain_over_incumbent"]))
    if baseline["gain_in_mean"] is not None:
        print("vs round 1      fresh designs average %+.3f %s on the un-guided scan"
              % (baseline["gain_in_mean"], obj["unit"]))
    print("wrote           %s" % os.path.relpath(path, args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
