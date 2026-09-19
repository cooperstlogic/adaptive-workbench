#!/usr/bin/env python3
"""Reconcile what the lab returned into evidence the project can use.

    python import_round.py --project projects/demo-trastuzumab --round 4 \
        --results /tmp/round4.csv

Reads a results CSV, writes evidence/snapshot_NNN.json.

The lab reports wells, not designs: rows keyed by the registry's sample id,
two reads per construct, about three percent of constructs failed outright,
some reads below the detection limit, and every well in the round carrying
whatever offset that run happened to have. This script joins on the external
reference table, checks units, averages replicates, keeps censored wells as
censored, estimates the round's offset from the designs shared with earlier
rounds, hashes the result into an immutable manifest, and sets the anomaly
flag.

It adds no arithmetic of its own. Every number comes from core/reconcile.py,
because simulate_campaign.py pools measurements too and a second
implementation of the bridging maths is the fork that would make the proof
chart and the product disagree.

**It never decides whether to correct.** Deciding that a round looks wrong is
a threshold and lives here. Deciding why, and therefore what to do about it,
is a judgment call. So the caller names what authorizes a correction and the
snapshot records it:

    --offset never                     the raw assay frame; the estimate is
                                       recorded and not applied
    --offset if-clear --authority X     correct a round that did not flag,
                                       which is routine control normalization
    --offset always --authority X       correct this round because something
                                       ruled that it should be

A flagged round under ``if-clear`` stays in the raw frame, because a flagged
round is one where an assay shift and a real structure-activity cliff produce
the same first look and correcting the wrong one erases the finding. Moving
such a round takes ``--offset always`` and an authority that names the
decision record.
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import numpy as np  # noqa: E402

from core import project, reconcile, schema, surrogate  # noqa: E402

REQUIRED = ("sample_id", "plate", "well", "assay_version", "replicate", "value", "unit", "status")


def read_results(path):
    """Parse the export as exported. Empty value means the construct failed."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError("results file is missing columns: %s" % ", ".join(missing))
        rows = []
        for raw in reader:
            row = dict(raw)
            schema.assert_unit(row["unit"], "assay read for %s" % row["sample_id"])
            row["replicate"] = int(row["replicate"])
            row["value"] = None if row["value"] in ("", None) else float(row["value"])
            rows.append(row)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--results", required=True, help="the assay export for this round")
    ap.add_argument("--offset", choices=("never", "if-clear", "always"), default="never",
                    help="when to move this round into the project frame by its bridge "
                         "estimate (default: never)")
    ap.add_argument("--authority", default=None, metavar="TEXT",
                    help="what authorizes the correction: a decision record id, or the "
                         "named policy that applies to rounds nobody had to rule on")
    args = ap.parse_args(argv)

    if args.offset != "never" and not args.authority:
        print("--offset %s needs --authority: a correction with nothing standing behind it "
              "is not recorded" % args.offset, file=sys.stderr)
        return 2

    state = project.load(args.project)
    obj = state["objectives"]
    batch = project.read_artifact(state, "batches", args.round)
    if batch is None:
        print("no batch for round %d; nothing was submitted" % args.round, file=sys.stderr)
        return 2

    rows = read_results(args.results)

    # The join. The registry's sample id is the only way back to a design, so
    # reconciliation is real work rather than a lookup by sequence.
    by_sample = project.sequence_by_sample(state)
    joined, unreconciled = [], []
    for row in rows:
        seq = by_sample.get(row["sample_id"])
        if seq is None:
            unreconciled.append(row["sample_id"])
            continue
        joined.append(dict(row, sequence=seq))
    if unreconciled:
        print("%d rows reference sample ids this project does not hold: %s"
              % (len(unreconciled), ", ".join(sorted(set(unreconciled))[:5])), file=sys.stderr)
        return 2

    aggregated = reconcile.aggregate_reads(joined)
    approved = set(batch["approved"])
    slot_of = {s["design_id"]: s for s in batch["slots"]}
    id_of = {s["sequence"]: s["design_id"] for s in batch["slots"]}
    returned = {id_of.get(seq) for seq in aggregated}
    absent = sorted(approved - {d for d in returned if d})
    extra = sorted({d for d in returned if d} - approved)

    versions = sorted({rec["assay_version"] for rec in aggregated.values()})
    if len(versions) != 1:
        print("a snapshot covers one assay version; this export has %s" % versions,
              file=sys.stderr)
        return 2
    version = versions[0]

    # The bridge: designs measured in this round that the project already
    # carries. The batch names them, and the batch deliberately excludes the
    # best-so-far control, which was selected for reading high and therefore
    # measures regression to the mean rather than a run offset.
    prior = reconcile.pool(project.measurement_records(state, through=args.round - 1))
    reference = {s: v["value"] for s, v in prior.items() if not v["censored"]}
    bridge_sequences = [slot_of[d]["sequence"] for d in batch["bridge"] if d in slot_of]
    estimate = reconcile.offset_from_bridge(aggregated, reference, designs=bridge_sequences)

    # The anomaly flag, computed on what the lab returned before any
    # correction -- which is the point. Scoped to this round's fresh designs:
    # letting the bridge into the flag would mean the alert had already decided
    # that the run moved rather than that the designs are genuinely worse.
    known = project.known_version_offsets(state, through=args.round - 1).get(version)
    flag = None
    fresh_ids = [d for d in batch["fresh"] if d in approved]
    predicted = [d for d in fresh_ids
                 if slot_of[d].get("pred_mean") is not None
                 and aggregated.get(slot_of[d]["sequence"], {}).get("value") is not None
                 and not aggregated[slot_of[d]["sequence"]]["censored"]]
    if len(predicted) >= int(obj["anomaly_flag"]["min_designs"]):
        mu = np.array([slot_of[d]["pred_mean"] for d in predicted], dtype=np.float64)
        sg = np.array([slot_of[d]["pred_sd"] for d in predicted], dtype=np.float64)
        got = np.array([aggregated[slot_of[d]["sequence"]]["value"] for d in predicted],
                       dtype=np.float64) - (known or 0.0)
        flag = reconcile.anomaly_flag(got, mu, sg, obj["anomaly_flag"])
        flag["assay_version"] = version
        flag["known_version_offset"] = known
        flag["compared_against"] = ("predictions recorded in batch_%03d from model run %03d"
                                    % (args.round, args.round - 1))

    flagged = bool(flag and flag["flagged"])
    apply_it = args.offset == "always" or (args.offset == "if-clear" and not flagged)
    offset_applied = float(estimate["offset"]) if apply_it else 0.0
    if apply_it and estimate["n"] == 0:
        offset_applied = 0.0
    corrected = reconcile.apply_offset(aggregated, offset_applied)

    if apply_it:
        authority, frame_note = args.authority, (
            "moved into the project frame by %+.3f %s under authority %r"
            % (offset_applied, obj["unit"], args.authority))
    elif flagged:
        authority, frame_note = "unruled", (
            "raw assay frame. The bridge estimate is recorded and not applied: this round "
            "is flagged, and an assay shift and a real structure-activity cliff produce the "
            "same first look, so correcting the wrong one would erase the finding")
    else:
        authority, frame_note = "not_applied", (
            "raw assay frame; the caller asked for no correction")

    measurements = []
    for seq, rec in corrected.items():
        did = id_of.get(seq)
        slot = slot_of.get(did, {})
        measurements.append({
            "design_id": did,
            "sequence": seq,
            "value": rec["value"],
            "raw_value": rec["raw_value"],
            "offset_applied": rec["offset_applied"],
            "status": rec["status"],
            "censored": rec["censored"],
            "partially_censored": rec["partially_censored"],
            "n_reads": rec["n_reads"],
            "n_ok": rec["n_ok"],
            "n_censored": rec["n_censored"],
            "n_failed": rec["n_failed"],
            "read_sd": rec["read_sd"],
            "plates": rec["plates"],
            "assay_version": rec["assay_version"],
            "unit": rec["unit"],
            "slot": slot.get("slot"),
            "bridge": did in set(batch["bridge"]),
            "fresh": did in set(batch["fresh"]),
        })
    measurements.sort(key=lambda m: batch["approved"].index(m["design_id"])
                      if m["design_id"] in approved else len(batch["approved"]))

    n_ok = sum(1 for m in measurements if m["status"] == reconcile.OK)
    n_cens = sum(1 for m in measurements if m["censored"])
    n_failed = sum(1 for m in measurements if m["status"] == reconcile.FAILED)

    record = schema.stamp({
        "schema_version": schema.SCHEMA_VERSION,
        "round": int(args.round),
        "unit": obj["unit"],
        "assay_version": version,
        "source": {
            "kind": state["project"]["sources"]["registry"]["kind"],
            "file": os.path.basename(args.results),
            "rows": len(rows),
        },
        "reconciliation": {
            "rows": len(rows),
            "samples": len({r["sample_id"] for r in joined}),
            "designs": len(measurements),
            "unreconciled_rows": 0,
            "approved_not_returned": absent,
            "returned_not_approved": extra,
            "n_ok": n_ok,
            "n_censored": n_cens,
            "n_failed": n_failed,
            "replicate_rule": "averaged over usable reads; a censored read says only "
                              "'less than', so averaging the limit into a real number "
                              "would invent a measurement",
            "censoring_rule": "kept as censored at the detection limit, carrying the flag",
        },
        "frame": {
            "offset_applied": offset_applied,
            "authority": authority,
            "offset_policy": args.offset,
            "offset_estimate": estimate,
            "known_version_offset": known,
            "note": frame_note,
        },
        "anomaly": flag,
        "flagged": flagged,
        "measurements": measurements,
    }, inputs={
        "batch": batch["hash"], "objectives": obj["hash"],
        "designs": state["designs"]["hash"],
    })

    path = project.artifact_path(state, "evidence", args.round)
    schema.write_json(path, record)
    project.link_round(state, args.round,
                       snapshot=project.artifact_ref(state["paths"]["root"], path, record),
                       flagged=record["flagged"])

    values = [m["value"] for m in measurements if m["value"] is not None]
    print("round           %d  assay version %s%s"
          % (args.round, version, "" if known is None else " (offset already characterized at "
             "%+.3f)" % known))
    print("rows            %d joined to %d designs through the reference table"
          % (len(rows), len(measurements)))
    print("returned        %d usable, %d censored at the limit, %d construct failures"
          % (n_ok, n_cens, n_failed))
    if absent:
        print("not returned    %d approved designs: %s" % (len(absent), ", ".join(absent[:4])))
    print("range           %.3f to %.3f %s" % (min(values), max(values), obj["unit"]))
    if estimate["n"]:
        print("bridge          %d designs, offset %+.3f %s%s"
              % (estimate["n"], estimate["offset"], obj["unit"],
                 "" if estimate["se"] is None else " (se %.3f)" % estimate["se"]))
    else:
        print("bridge          none usable; %s" % estimate.get("note", ""))
    print("frame           offset applied %+.3f, authority %s"
          % (offset_applied, record["frame"]["authority"]))
    if flag is None:
        print("anomaly flag    not computed: no prior model predictions for this round's designs")
    else:
        print("anomaly flag    %s  mean signed residual %+.3f %s over %d fresh designs "
              "(trigger %.2f)"
              % ("RAISED" if flag["flagged"] else "clear", flag["mean_signed_residual"],
                 obj["unit"], flag["n_compared"], flag["trigger_abs_pkd"]))
        print("                interval miss rate %.2f against an expected %.2f (reported, "
              "not triggered on)" % (flag["outside_interval"], flag["expected_outside"]))
    if record["flagged"]:
        print("                this round needs a ruling before its frame moves; "
              "run the diagnosis and record a decision")
    print("wrote           %s" % os.path.relpath(path, args.project))
    return 0


if __name__ == "__main__":
    sys.exit(main())
