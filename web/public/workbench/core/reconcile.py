"""Turning what the lab returned into measurements in the project's frame.

The lab reports wells, not designs: two reads per construct, some constructs
failed outright, some reads below the detection limit, and every well in a
round carrying whatever offset that run happened to have. Reconciling that is
real work, and it is the work ``import_round`` exists to do.

This lives in ``core/`` rather than inside the import script for one reason:
``simulate_campaign.py`` has to pool measurements across rounds too, and a
second implementation of the bridging arithmetic is exactly the fork that
would make the proof chart and the product disagree.

Nothing here reads ground truth. It sees only rows a lab returned.
"""

import numpy as np

from . import schema

OK = "ok"
FAILED = "failed"
CENSORED = "censored_low"


def aggregate_reads(rows, unit=schema.UNIT):
    """Replicate reads -> one record per design.

    A design whose construct failed has no value at all. A design whose reads
    all came back below the limit is censored and enters later arithmetic at
    the limit, carrying the flag. A design with some usable reads is averaged
    over those, because a censored read says only 'less than', and averaging
    the limit into a real number would invent a measurement.
    """
    order, grouped = [], {}
    for row in rows:
        schema.assert_unit(row.get("unit"), "assay read")
        seq = row["sequence"]
        if seq not in grouped:
            grouped[seq] = []
            order.append(seq)
        grouped[seq].append(row)

    out = {}
    for seq in order:
        reads = grouped[seq]
        ok = [r for r in reads if r["status"] == OK]
        cens = [r for r in reads if r["status"] == CENSORED]
        failed = [r for r in reads if r["status"] == FAILED]
        rec = {
            "sequence": seq,
            "n_reads": len(reads),
            "n_ok": len(ok),
            "n_censored": len(cens),
            "n_failed": len(failed),
            "plates": sorted({str(r.get("plate")) for r in reads if r.get("plate") is not None}),
            "assay_version": reads[0].get("assay_version"),
            "unit": unit,
        }
        if ok:
            vals = np.array([float(r["value"]) for r in ok])
            rec.update({
                "value": float(vals.mean()),
                "read_sd": float(vals.std(ddof=1)) if len(vals) > 1 else None,
                "status": OK,
                "censored": False,
                "partially_censored": bool(cens),
            })
        elif cens:
            rec.update({
                "value": float(cens[0]["value"]),
                "read_sd": None,
                "status": CENSORED,
                "censored": True,
                "partially_censored": False,
            })
        else:
            rec.update({
                "value": None, "read_sd": None, "status": FAILED,
                "censored": False, "partially_censored": False,
            })
        out[seq] = rec
    return out


def bridge_designs(aggregated, reference):
    """Designs usable for estimating this round's offset.

    Usable means measured in this round and already carried in the project
    frame, with a real value on both sides. A censored well says only that the
    value is below the limit, so it cannot tell you how far the run moved.
    """
    return [
        s for s, rec in aggregated.items()
        if s in reference and rec.get("value") is not None and not rec.get("censored")
    ]


def offset_from_bridge(aggregated, reference, designs=None):
    """-> {offset, se, n, designs, per_design}.

    The offset is the mean shift of the shared designs. Its standard error is
    what turns 'the round looks low' into a number with a scale attached, and
    it is the evidence the round-4 diagnosis rests on.
    """
    designs = list(designs) if designs is not None else bridge_designs(aggregated, reference)
    diffs, used = [], []
    for s in designs:
        rec = aggregated.get(s)
        if rec is None or rec.get("value") is None or rec.get("censored"):
            continue
        if s not in reference:
            continue
        diffs.append(float(rec["value"]) - float(reference[s]))
        used.append({"sequence": s, "current": float(rec["value"]),
                     "reference": float(reference[s]), "delta": diffs[-1]})
    n = len(diffs)
    if n == 0:
        return {"offset": 0.0, "se": None, "n": 0, "designs": [], "per_design": [],
                "note": "no usable bridge designs; offset assumed zero"}
    arr = np.array(diffs, dtype=np.float64)
    se = float(arr.std(ddof=1) / np.sqrt(n)) if n > 1 else None
    return {
        "offset": float(arr.mean()),
        "se": se,
        "n": n,
        "designs": [u["sequence"] for u in used],
        "per_design": used,
    }


def apply_offset(aggregated, offset):
    """Move a round into the project frame, keeping the raw value beside it.

    Censored records are shifted too: the detection limit is a property of the
    assay, so in the project's frame it moves with everything else.
    """
    offset = float(offset)
    out = {}
    for seq, rec in aggregated.items():
        new = dict(rec)
        new["raw_value"] = rec.get("value")
        new["offset_applied"] = offset
        if rec.get("value") is not None:
            new["value"] = float(rec["value"]) - offset
        out[seq] = new
    return out


def pool(records):
    """Fold per-round records into one value per design in the project frame.

    A design measured in several rounds is averaged over its corrected
    measurements, which is the point of correcting them. A design that is only
    ever censored stays censored.
    """
    acc = {}
    for rec in records:
        if rec.get("value") is None:
            continue
        seq = rec["sequence"]
        slot = acc.setdefault(seq, {"sequence": seq, "values": [], "censored": [], "rounds": []})
        slot["values"].append(float(rec["value"]))
        slot["censored"].append(bool(rec.get("censored")))
        if rec.get("round") is not None:
            slot["rounds"].append(int(rec["round"]))
    out = {}
    for seq, slot in acc.items():
        vals = np.array(slot["values"], dtype=np.float64)
        out[seq] = {
            "sequence": seq,
            "value": float(vals.mean()),
            "n_measurements": int(vals.size),
            "censored": bool(all(slot["censored"])),
            "any_censored": bool(any(slot["censored"])),
            "rounds": sorted(slot["rounds"]),
        }
    return out


def interval_miss_rate(observed, pred_mean, pred_sd, interval=0.80):
    """Fraction of designs falling outside the model's central interval."""
    from .surrogate import z_for_central

    observed = np.asarray(observed, dtype=np.float64)
    pred_mean = np.asarray(pred_mean, dtype=np.float64)
    pred_sd = np.maximum(np.asarray(pred_sd, dtype=np.float64), 1e-9)
    z = z_for_central(interval)
    outside = np.abs(observed - pred_mean) > z * pred_sd
    return float(np.mean(outside)) if observed.size else 0.0


def mean_signed_residual(observed, pred_mean):
    """How far this round sits from where the model put it, and in which direction."""
    r = np.asarray(observed, dtype=np.float64) - np.asarray(pred_mean, dtype=np.float64)
    n = int(r.size)
    if n == 0:
        return {"mean": 0.0, "se": None, "z": None, "n": 0}
    se = float(r.std(ddof=1) / np.sqrt(n)) if n > 1 else None
    return {"mean": float(r.mean()), "se": se,
            "z": (float(r.mean() / se) if se and se > 0 else None), "n": n}


def anomaly_flag(observed, pred_mean, pred_sd, policy):
    """Does this round *look* wrong? A threshold, and only a threshold.

    Deciding that a round looks wrong is arithmetic and belongs in code.
    Deciding why is the judgment call, and it is the one the agent is for.

    The statistic is the mean *signed* discrepancy between what came back and
    what the model predicted, over this round's fresh designs. Signed, because
    "everything came back low" is what a scientist means by a round looking
    wrong, while "everything came back scattered" is what a batch chosen by
    expected improvement looks like on any round at all -- acquisition samples
    where the model is least certain, so a dispersion statistic fires every
    time and tells you nothing.

    It is deliberately a statistic that a run offset and a real structure-
    activity cliff trip in exactly the same way. The flag says a round needs
    deciding. It does not say which explanation wins, and it is not allowed to.

    The interval miss rate is still returned, because the calibration panel
    wants it -- it is reported, not triggered on.
    """
    trigger = float(policy.get("trigger_abs_pkd", 0.5))
    minimum = int(policy.get("min_designs", 8))
    interval = float(policy.get("interval", 0.80))
    stat = mean_signed_residual(observed, pred_mean)
    flagged = bool(stat["n"] >= minimum and abs(stat["mean"]) > trigger)
    return {
        "flagged": flagged,
        "statistic": "mean_signed_residual",
        "mean_signed_residual": stat["mean"],
        "se": stat["se"],
        "z": stat["z"],
        "direction": "below prediction" if stat["mean"] < 0 else "above prediction",
        "trigger_abs_pkd": trigger,
        "min_designs": minimum,
        "n_compared": stat["n"],
        "outside_interval": interval_miss_rate(observed, pred_mean, pred_sd, interval),
        "interval": interval,
        "expected_outside": float(policy.get("expected_outside", 1.0 - interval)),
    }
