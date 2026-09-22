#!/usr/bin/env python3
"""Choose the next batch: controls, replicates, exploration slots, fresh picks.

    python select_batch.py --project projects/demo-trastuzumab --round 2
    python select_batch.py --project ... --round 2 \
        --approved-by d.webster --drop 4f2a91c3e8d0 --drop-note "known expression risk"
    python select_batch.py --project ... --round 2 \
        --set batch.exploration_slots=4 --set-note "two slots is not enough coverage"

Reads candidates/pool_NNN.json and the previous model run, writes
batches/batch_NNN.json.

The record separates what was proposed from what was run. ``recommended`` is
what the optimizer returned, ``approved`` is what a named person let through,
and ``overrides`` records each removal with a note and a timestamp. That is
the governance claim in one file: the system proposes, a person disposes, and
the evaluation step scores predictions for what was actually tested.

``--drop`` overrides the optimizer's *output*. ``--set`` overrides its
*input*: re-compose this batch with a different number of exploration slots,
replicates, controls, or a different diversity weight, bounded by the same
`core.amend` list an amendment is held to. It touches nothing but this batch
-- ``objectives.json`` is not written, and the next round reverts to the
declaration -- so it needs no ruling behind it. **What gates it is the
approval that gates every batch**, which has not happened yet and is the only
thing that sends wells to a laboratory. A round that has been submitted
refuses the flag outright, because its batch record is the order that went
out.

Round 1 needs no separate script. With no model run on disk there is nothing
to exploit, so the seed branch returns the template's round-1 policy batch and
says so in the rationale -- the same code path, one branch deep.
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import numpy as np  # noqa: E402

from core import (acquisition, amend, candidates, encode, project, reconcile, schema,  # noqa: E402
                  surrogate)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def seed_batch(pool, parent, region, policy):
    """Round 1: no model, so diversity over the pool under the template policy."""
    batch, draw = candidates.round1_batch(
        pool, parent, region, int(policy["size"]),
        policy.get("round1_policy", "diversity"), policy.get("round1_scan_residues",
                                                             candidates.SCAN_RESIDUES))
    name = policy.get("round1_policy", "diversity")
    rationale = ("round-1 %s over %d of %d feasible candidates; no model run exists yet, "
                 "so there is nothing to exploit" % (name, len(draw), len(pool)))
    slots = [{"sequence": s, "slot": "pick", "rationale": rationale, "bridge": False,
              "n_mutations": encode.n_mutations(parent, s, region),
              "previously_measured": False}
             for s in batch]
    return {
        "slots": slots, "sequences": list(batch), "size": len(batch),
        "requested_size": int(policy["size"]), "mode": "seed",
        "composition": {"control": 0, "replicate": 0, "exploration": 0, "pick": len(batch)},
        "bridge": [], "re_measured": [], "fresh": list(batch),
        "diversity_weight": None, "incumbent": None, "extrapolation_cut_sd": None,
        "round1_policy": name, "round1_draw_size": len(draw),
        "min_pairwise_distance": float(candidates.max_min_distance(batch, region)),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--approved-by", default=None,
                    help="the person approving the batch; without it the batch is unreviewed")
    ap.add_argument("--drop", action="append", default=[], metavar="DESIGN_ID",
                    help="remove a recommended design from the approved list; repeatable")
    ap.add_argument("--drop-note", action="append", default=[], metavar="NOTE",
                    help="the reason for the matching --drop")
    ap.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                    dest="set_",
                    help="re-compose this batch under a changed policy field, e.g. "
                         "batch.exploration_slots=4; repeatable. The declaration is not "
                         "touched and the next round reverts to it")
    ap.add_argument("--set-note", default="", metavar="NOTE",
                    help="why the policy was overridden for this batch")
    ap.add_argument("--set-by", default=None, metavar="WHO",
                    help="who asked for the override")
    args = ap.parse_args(argv)

    state = project.load(args.project)
    obj = state["objectives"]
    parent, region, policy = state["designs"]["parent"], obj["editable_region"], obj["batch"]

    # A policy override re-composes *this* batch and nothing else. It is only
    # available while the round is still here: once it has been submitted, the
    # batch record is what the laboratory's order was built from, and
    # rewriting it would be falsifying the account of what was sent.
    overrides_policy = []
    if args.set_:
        entry = next((e for e in state["rounds"]["rounds"]
                      if int(e["round"]) == int(args.round)), None)
        if entry and entry.get("submission"):
            print("round %d has been submitted, so its batch is the order the laboratory "
                  "received and is not re-composable. A policy change from here is an "
                  "amendment on a decision record" % args.round, file=sys.stderr)
            return 2
        pairs = []
        for item in args.set_:
            if "=" not in item:
                print("--set takes FIELD=VALUE; %r has no '='" % item, file=sys.stderr)
                return 2
            field, _, raw = item.partition("=")
            pairs.append((field.strip(), raw.strip()))
        try:
            policy, overrides_policy = amend.plan_overrides(obj, pairs)
        except amend.Refused as why:
            print("refused: %s" % why, file=sys.stderr)
            return 2
        stamped = _now()
        for rec in overrides_policy:
            rec.update(by=args.set_by, note=args.set_note, at=stamped)

    pool_rec = project.read_artifact(state, "candidates", args.round)
    if pool_rec is None:
        print("no candidate pool for round %d; run generate_candidates.py first" % args.round,
              file=sys.stderr)
        return 2
    kept, _, _ = project.feasible_pool(state)
    if project.pool_fingerprint(kept) != pool_rec["pool_fingerprint"]:
        print("the feasible pool no longer hashes to what pool_%03d.json recorded; "
              "objectives or constraints have changed" % args.round, file=sys.stderr)
        return 2

    prior_run = project.read_artifact(state, "models", args.round - 1)
    records = project.measurement_records(state, through=args.round - 1)
    observed = reconcile.pool(records)

    if prior_run is None:
        if observed:
            print("round %d has measurements but no model run for round %d; "
                  "run fit_surrogates.py first" % (args.round, args.round - 1), file=sys.stderr)
            return 2
        batch = seed_batch(kept, parent, region, policy)
        winner = None
    else:
        if prior_run["pool_fingerprint"] != pool_rec["pool_fingerprint"]:
            print("model run %03d was fit against a different candidate pool"
                  % (args.round - 1), file=sys.stderr)
            return 2
        features = surrogate.Features(kept, region)
        mean = np.array(prior_run["pool_mean"], dtype=np.float64)
        sd = np.array(prior_run["pool_sd"], dtype=np.float64)
        incumbent = max(v["value"] for v in observed.values())
        prev = project.read_artifact(state, "batches", args.round - 1)
        batch = acquisition.compose_batch(
            features, policy, parent=parent, observed=observed,
            previous_batch=(prev or {}).get("approved_sequences"),
            mean=mean, sd=sd, incumbent=incumbent, objectives=obj["objectives"],
            mode="guided",
            # Absent from a project the template instantiated, so the module
            # default stands and every existing store is byte-for-byte
            # unaffected. It is here because it is amendable: the diversity
            # penalty is the other half of "explore more", and a policy that
            # can add exploration slots but not loosen the penalty can only
            # ask for uncertainty it has already ranked.
            diversity_weight=float(policy.get("diversity_weight",
                                              acquisition.DIVERSITY_WEIGHT)))
        batch["min_pairwise_distance"] = float(
            candidates.max_min_distance(batch["sequences"], region))
        winner = prior_run["winner"]

    # Designs enter the project when they are recommended, which is what makes
    # the override path recordable: a dropped design is still a design that was
    # proposed, and designs.json is where that history lives.
    project.add_designs(state, batch["sequences"],
                        origin="round%d_%s" % (args.round, batch["mode"]), round_id=args.round)
    ids = {s["sequence"]: encode.sequence_id(s["sequence"]) for s in batch["slots"]}
    scored = {d["design_id"]: d["computed"] for d in state["designs"]["designs"]}

    slots = []
    for rec in batch["slots"]:
        did = ids[rec["sequence"]]
        slots.append(dict(rec, design_id=did, computed=scored[did]))
    plates = acquisition.assign_plates(batch["sequences"], args.round)
    for rec, plate in zip(slots, plates):
        rec["plate_planned"] = plate

    recommended = [r["design_id"] for r in slots]
    notes = list(args.drop_note) + [""] * max(0, len(args.drop) - len(args.drop_note))
    overrides, dropped = [], set()
    for did, note in zip(args.drop, notes):
        if did not in recommended:
            print("--drop %s is not in the recommended batch" % did, file=sys.stderr)
            return 2
        dropped.add(did)
        overrides.append({"design_id": did, "action": "removed", "note": note,
                          "by": args.approved_by, "at": _now()})
    approved = [d for d in recommended if d not in dropped]
    by_id = {r["design_id"]: r for r in slots}

    body = {
        "schema_version": schema.SCHEMA_VERSION,
        "round": int(args.round),
        "unit": obj["unit"],
        "mode": batch["mode"],
        # The policy this batch was actually composed under, which is the
        # declaration's unless it was overridden. `policy_overrides` then says
        # what the declaration said instead, and it is present only when there
        # were any -- so every batch selected before this flag existed hashes
        # to exactly what it hashed to.
        "policy": policy,
        "model_run": None if prior_run is None else project.artifact_ref(
            state["paths"]["root"],
            project.artifact_path(state, "models", args.round - 1), prior_run),
        "model_winner": winner,
        "n_observed": len(observed),
        "incumbent": batch["incumbent"],
        "diversity_weight": batch["diversity_weight"],
        "extrapolation_cut_sd": batch["extrapolation_cut_sd"],
        "min_pairwise_distance": batch["min_pairwise_distance"],
        "composition": batch["composition"],
        "slots": slots,
        "recommended": recommended,
        "approved": approved,
        "approved_sequences": [by_id[d]["sequence"] for d in approved],
        "overrides": overrides,
        "bridge": [ids[s] for s in batch["bridge"]],
        "fresh": [ids[s] for s in batch["fresh"]],
        "re_measured": [ids[s] for s in batch["re_measured"]],
        "approval": {
            "status": "approved" if args.approved_by else "unreviewed",
            "by": args.approved_by,
            "at": _now() if args.approved_by else None,
            "note": ("no reviewer was named on this run, so the batch carries what the "
                     "optimizer recommended and says so"
                     if not args.approved_by else ""),
        },
        "round1_policy": batch.get("round1_policy"),
        "round1_draw_size": batch.get("round1_draw_size"),
    }
    if overrides_policy:
        body["policy_overrides"] = overrides_policy
    record = schema.stamp(body, inputs={
        "objectives": obj["hash"], "pool": pool_rec["hash"],
        "designs": state["designs"]["hash"],
        "model_run": None if prior_run is None else prior_run["hash"],
    })

    path = project.artifact_path(state, "batches", args.round)
    schema.write_json(path, record)
    project.link_round(state, args.round,
                       batch=project.artifact_ref(state["paths"]["root"], path, record))

    comp = record["composition"]
    print("round           %d  (%s)" % (args.round, batch["mode"]))
    print("model           %s" % (winner or "none yet; seed branch"))
    print("composition     %d wells = %d control, %d replicate, %d exploration, %d fresh picks"
          % (len(slots), comp["control"], comp["replicate"], comp["exploration"], comp["pick"]))
    print("bridge          %d designs shared with earlier rounds" % len(record["bridge"]))
    if batch["incumbent"] is not None:
        print("incumbent       %.3f %s" % (batch["incumbent"], obj["unit"]))
    extrap = sum(1 for s in slots if s.get("extrapolation"))
    if prior_run is not None:
        print("extrapolating   %d of %d slots sit above the %.0fth uncertainty percentile"
              % (extrap, len(slots), acquisition.EXTRAPOLATION_PERCENTILE))
    for rec in overrides_policy:
        print("policy override %s %s -> %s%s"
              % (rec["field"], rec["from"], rec["to"],
                 "" if not rec["by"] else "  (asked by %s)" % rec["by"]))
    if overrides_policy:
        print("                this batch only; objectives.json is untouched and round %d "
              "reverts to it" % (args.round + 1))
    print("approval        %s%s" % (record["approval"]["status"],
                                    "" if not args.approved_by else " by " + args.approved_by))
    if overrides:
        print("overrides       %d removed: %s"
              % (len(overrides), ", ".join("%s (%s)" % (o["design_id"], o["note"] or "no note")
                                           for o in overrides)))
    print("approved        %d of %d recommended" % (len(approved), len(recommended)))
    print("wrote           %s" % os.path.relpath(path, args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
