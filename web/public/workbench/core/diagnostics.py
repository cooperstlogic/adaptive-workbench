"""The five library diagnostics a flagged round is read with.

A flagged round is one where the returned measurements sit further from the
model's predictions than the template's trigger allows. That is arithmetic and
``reconcile.anomaly_flag`` does it. *Why* they sit there has four standard
explanations -- a run or assay-version offset, a plate artifact, the model
extrapolating, or a real structure-activity cliff -- and the first and last
produce the same first look and demand opposite actions.

These five functions are the evidence the choice between them is made on. They
are read-only, they take the project's own records, and each returns numbers
and nothing else. Every judgment about what the numbers mean is the agent's,
and every number in a decision record comes from one of these.

Two rules hold the boundary:

* **No test decides anything.** A result may carry a factual note giving a
  number its scale -- "spread 0.10 against a read-noise scale of 0.17" -- and
  never a verdict. `supported` and `not supported` are the agent's words.
* **No test recomputes something the project already recorded.**
  ``offset_from_controls`` reads the bridge estimate ``import_round`` wrote
  with ``reconcile.offset_from_bridge`` rather than estimating its own, so a
  diagnostic and a snapshot cannot disagree about the same quantity.

Nothing here reads ground truth, and nothing here writes.
"""

import numpy as np

from . import surrogate

TESTS = (
    "offset_from_controls",
    "residual_by_plate",
    "residual_by_mutation_class",
    "replicate_concordance",
    "calibration_by_region",
)

MUTATION_CLASS_BY = ("position", "n_mutations")


def _stats(values):
    """n, mean, sd and se for a group. sd is None for a group of one."""
    a = np.asarray(list(values), dtype=np.float64)
    if a.size == 0:
        return {"n": 0, "mean": None, "sd": None, "se": None}
    sd = float(a.std(ddof=1)) if a.size > 1 else None
    return {"n": int(a.size), "mean": float(a.mean()), "sd": sd,
            "se": None if sd is None else float(sd / np.sqrt(a.size))}


def _grouped(table, key_of):
    """-> {key: [rows]}, where a row may belong to more than one group."""
    out = {}
    for row in table:
        for key in key_of(row):
            out.setdefault(key, []).append(row)
    return out


def residual_table(snapshot, batch, designs=None):
    """The join every test reads: what came back against what was predicted.

    One row per design that the project both predicted and measured usably --
    so construct failures, censored wells and designs carrying no prediction
    are absent, and the counts say so. The predictions are the ones recorded
    in the batch at selection time, which is the honest comparison: it is what
    the project believed when it spent the wells.

    This is the only join in the diagnostics, and it lives in ``core/`` so the
    CLI, the connectors and the browser read it from one implementation.
    """
    slot_of = {s["design_id"]: s for s in batch["slots"]}
    by_id = designs or {}
    approved = set(batch["approved"])
    rows = []
    for m in snapshot["measurements"]:
        slot = slot_of.get(m["design_id"])
        if slot is None or m["design_id"] not in approved:
            continue
        if slot.get("pred_mean") is None or m["value"] is None or m["censored"]:
            continue
        design = by_id.get(m["design_id"], {})
        rows.append({
            "design_id": m["design_id"],
            "observed": float(m["value"]),
            "pred_mean": float(slot["pred_mean"]),
            "pred_sd": float(slot["pred_sd"]),
            "residual": float(m["value"]) - float(slot["pred_mean"]),
            "plates": list(m.get("plates") or []),
            "slot": m.get("slot"),
            "fresh": bool(m.get("fresh")),
            "bridge": bool(m.get("bridge")),
            "read_sd": m.get("read_sd"),
            "n_ok": int(m.get("n_ok", 0)),
            "mutations": list(design.get("mutations", [])),
            "n_mutations": design.get("n_mutations"),
            "extrapolation": bool(slot.get("extrapolation")),
        })
    return rows


def read_noise_scale(table):
    """The round's own estimate of assay read noise, in pKD.

    Two reads of one construct differ only by read noise, so the root mean
    square of the per-design read spread is an estimate of that noise made
    from this round alone -- no pre-registered constant, nothing from the
    oracle. It is the scale the concordance and outlier tests measure against,
    which is what keeps them from inheriting a number nobody checked.
    """
    sds = [float(r["read_sd"]) for r in table if r.get("read_sd") is not None]
    if not sds:
        return None
    return float(np.sqrt(np.mean(np.square(np.asarray(sds, dtype=np.float64)))))


def offset_from_controls(snapshot, table, concordance_k=2.0):
    """The recorded bridge offset, plus whether its members agree with it.

    The offset itself is not recomputed: ``import_round`` already estimated it
    with ``reconcile.offset_from_bridge`` over the designs this round shares
    with earlier ones, and hashed it into the snapshot. What this adds is the
    question that decides whether the offset may be used at all -- do the
    shared designs, which are the same molecules measured twice, tell the same
    story? If they do not, there is no single number to correct by.
    """
    est = dict(snapshot["frame"]["offset_estimate"])
    deltas = [float(d["delta"]) for d in est.get("per_design", [])]
    noise = read_noise_scale(table)
    spread = _stats(deltas)
    tol = None if noise is None else float(concordance_k * noise)
    concordant = None if (spread["sd"] is None or tol is None) else bool(spread["sd"] <= tol)
    return {
        "test": "offset_from_controls", "unit": snapshot["unit"],
        "offset_pkd": est["offset"], "se": est["se"], "n_bridge": est["n"],
        "per_design_delta": [round(d, 6) for d in deltas],
        "delta_sd": spread["sd"], "delta_range": (max(deltas) - min(deltas)) if deltas else None,
        "read_noise_scale": noise, "concordance_k": float(concordance_k),
        "concordance_tolerance": tol, "concordant": concordant,
        "assay_version": snapshot["assay_version"],
        "known_version_offset": snapshot["frame"].get("known_version_offset"),
        "note": ("bridge of %d; spread sd %s against a tolerance of %s, being %.1f x the "
                 "round's read-noise scale %s"
                 % (est["n"], _fmt(spread["sd"]), _fmt(tol), concordance_k, _fmt(noise))),
    }


def residual_by_plate(table):
    """Mean residual by plate, and whether the plates separate.

    A plate artifact moves one plate and leaves the other where it was. A run
    offset moves both by the same amount, so this test cannot see it -- which
    is the point of running it second.

    A design whose reads were split across plates counts in both, as it should
    -- so the group sizes can sum to more than the number of designs, and they
    are reported rather than assumed.
    """
    groups = _grouped(table, lambda r: r["plates"])
    per = {k: _stats([r["residual"] for r in v]) for k, v in sorted(groups.items())}
    means = [s["mean"] for s in per.values() if s["mean"] is not None]
    ses = [s["se"] for s in per.values() if s["se"] is not None]
    gap = (max(means) - min(means)) if len(means) > 1 else None
    se_gap = float(np.sqrt(sum(s * s for s in ses))) if len(ses) > 1 else None
    return {
        "test": "residual_by_plate", "n": len(table), "by_plate": per,
        "max_gap": gap, "se_of_gap": se_gap,
        "z_of_gap": (None if not (gap and se_gap) else float(gap / se_gap)),
        "overall": _stats([r["residual"] for r in table]),
        "note": ("%d plates; largest difference between plate means %s against a standard "
                 "error of %s" % (len(per), _fmt(gap), _fmt(se_gap))),
    }


def residual_by_mutation_class(table, by="position"):
    """Mean residual by mutation class, each class against everything else.

    ``by="position"`` asks whether one edited position carries the round, which
    is the test a structure-activity cliff has to pass: a cliff lives at one
    position, so if the position it lives at looks like the others, it is not
    what moved the round. ``by="n_mutations"`` asks whether the round's
    surprise scales with how far the designs are from the parent, which is what
    a model extrapolating past its training set looks like.

    ``n`` matters as much as the mean here. A cause that could explain a whole
    round has to appear in a class large enough to move it, and a class of two
    cannot.
    """
    if by == "n_mutations":
        key_of = (lambda r: [] if r["n_mutations"] is None else [int(r["n_mutations"])])
    elif by == "position":
        key_of = lambda r: sorted({int(m[1:-1]) for m in r["mutations"]})
    else:
        raise ValueError("mutation class must be one of %s" % (MUTATION_CLASS_BY,))

    groups, classes = _grouped(table, key_of), {}
    for key, rows in sorted(groups.items()):
        ids = {r["design_id"] for r in rows}
        rest = [r["residual"] for r in table if r["design_id"] not in ids]
        here, other = _stats([r["residual"] for r in rows]), _stats(rest)
        classes[str(key)] = {
            "n": here["n"], "n_fresh": sum(1 for r in rows if r["fresh"]),
            "mean_residual": here["mean"], "sd": here["sd"], "se": here["se"],
            "n_other": other["n"], "mean_other": other["mean"],
            "vs_other_classes": (None if here["mean"] is None or other["mean"] is None
                                 else here["mean"] - other["mean"]),
        }
    spread = [c["mean_residual"] for c in classes.values() if c["mean_residual"] is not None]
    span = (max(spread) - min(spread)) if len(spread) > 1 else None
    overall = _stats([r["residual"] for r in table])
    return {
        "test": "residual_by_mutation_class", "by": by, "n": len(table),
        "classes": classes, "range_of_class_means": span, "overall": overall,
        "note": ("%d classes by %s; class means span %s around an overall %s. A design with "
                 "two mutations belongs to two position classes, so the classes overlap and "
                 "n is what says whether a class could move the round"
                 % (len(classes), by, _fmt(span), _fmt(overall["mean"]))),
    }


def replicate_concordance(table, outlier_k=3.0):
    """Spread between the reads of one construct, against the round's noise.

    Wide replicate spread says the assay was unstable while the plate was
    read, and it points at the measurement before any explanation that is
    about the molecules. A design flagged here is one whose two reads disagree
    by more than the round's own noise scale allows.
    """
    noise = read_noise_scale(table)
    measured = [r for r in table if r.get("read_sd") is not None]
    tol = None if noise is None else float(outlier_k * noise)
    flagged = [] if tol is None else [
        {"design_id": r["design_id"], "read_sd": float(r["read_sd"]), "slot": r["slot"]}
        for r in measured if float(r["read_sd"]) > tol
    ]
    sds = [float(r["read_sd"]) for r in measured]
    return {
        "test": "replicate_concordance", "n_with_replicates": len(measured),
        "n_single_read": sum(1 for r in table if r.get("read_sd") is None),
        "read_noise_scale": noise, "outlier_k": float(outlier_k), "tolerance": tol,
        "max_read_sd": max(sds) if sds else None,
        "median_read_sd": float(np.median(sds)) if sds else None,
        "n_flagged": len(flagged), "flagged": sorted(flagged, key=lambda f: -f["read_sd"]),
        "note": ("%d designs with two usable reads, noise scale %s, %d above the %s tolerance"
                 % (len(measured), _fmt(noise), len(flagged), _fmt(tol))),
    }


def calibration_by_region(table, interval=0.80, bins=4, offset=0.0):
    """Coverage of the predictive interval, overall and by predicted value.

    Coverage is the number that says whether the model's uncertainty can be
    trusted, and splitting it by predicted value says *where* it cannot: a
    model that is calibrated in the middle and badly wrong at the top of its
    own prediction range is extrapolating, and no correction to the data fixes
    that.

    ``offset`` is the counterfactual that separates the two explanations. Pass
    the bridge estimate and the result answers the question a correction is
    really making -- if this round were only an assay shift, moving it by the
    shift would restore coverage. Whatever coverage is still missing is not
    the assay.
    """
    z = surrogate.z_for_central(interval)
    rows = sorted(table, key=lambda r: r["pred_mean"])
    resid = np.array([r["residual"] - float(offset) for r in rows], dtype=np.float64)
    sd = np.array([r["pred_sd"] for r in rows], dtype=np.float64)
    inside = np.abs(resid) <= z * sd
    by_bin = []
    for part in (np.array_split(np.arange(len(rows)), bins) if rows else []):
        if not part.size:
            continue
        by_bin.append({
            "n": int(part.size),
            "pred_min": float(rows[part[0]]["pred_mean"]),
            "pred_max": float(rows[part[-1]]["pred_mean"]),
            "coverage": float(inside[part].mean()),
            "mean_residual": float(resid[part].mean()),
        })
    return {
        "test": "calibration_by_region", "n": len(rows), "interval": float(interval),
        "nominal_coverage": float(interval), "bins": int(bins),
        "offset_applied": float(offset),
        "coverage": float(inside.mean()) if len(rows) else None,
        "mean_residual": float(resid.mean()) if len(rows) else None,
        "by_predicted_value": by_bin,
        "note": ("%d designs, %s bins by predicted value%s"
                 % (len(rows), bins,
                    "" if not offset else
                    "; residuals shifted by %+.3f before scoring, so this is the coverage a "
                    "correction of that size would leave" % offset)),
    }


DEFAULT_POLICY = {"interval": 0.80, "bridge_concordance_k": 2.0,
                  "replicate_outlier_k": 3.0, "calibration_bins": 4}

OFFSET_SOURCES = ("none", "bridge")


def offset_argument(snapshot, source):
    """Resolve ``calibration_by_region``'s counterfactual shift.

    It is a named source and never a number the caller supplies. ``bridge``
    is the estimate ``reconcile.offset_from_bridge`` produced and the snapshot
    recorded; there is no third option, because a shift typed by hand would be
    a number entering a code path from outside ``core/``, which is the one
    thing the whole arrangement exists to prevent.
    """
    if source in (None, "none"):
        return 0.0
    if source == "bridge":
        return float(snapshot["frame"]["offset_estimate"]["offset"])
    raise ValueError("offset source must be one of %s, not %r" % (OFFSET_SOURCES, source))


def run(name, snapshot, batch, designs=None, policy=None, args=None):
    """Run one named test and return its result with how it was run attached.

    The single entry point, so the CLI, the decision writer and the browser
    cannot run the same test three slightly different ways. ``args`` is the
    agent's choice of *how* -- which class to group by, whether to score the
    counterfactual -- and it is echoed into the result, because a number that
    cannot be reproduced from what is recorded beside it is not evidence.
    """
    if name not in TESTS:
        raise ValueError("%r is not a library diagnostic; the five are %s" % (name, TESTS))
    policy = dict(DEFAULT_POLICY, **{k: v for k, v in (policy or {}).items() if k in DEFAULT_POLICY})
    args = dict(args or {})
    scope = args.get("scope", "all")
    if scope not in ("all", "fresh"):
        raise ValueError("scope must be 'all' or 'fresh', not %r" % scope)

    table = residual_table(snapshot, batch, designs)
    if scope == "fresh":
        table = [r for r in table if r["fresh"]]

    if name == "offset_from_controls":
        result = offset_from_controls(snapshot, table, policy["bridge_concordance_k"])
    elif name == "residual_by_plate":
        result = residual_by_plate(table)
    elif name == "residual_by_mutation_class":
        result = residual_by_mutation_class(table, by=args.get("by", "position"))
    elif name == "replicate_concordance":
        result = replicate_concordance(table, policy["replicate_outlier_k"])
    else:
        result = calibration_by_region(table, policy["interval"], policy["calibration_bins"],
                                       offset=offset_argument(snapshot, args.get("offset")))

    result["round"] = int(snapshot["round"])
    result["scope"] = scope
    result["n_scored"] = len(table)
    result["frame"] = {"offset_applied": snapshot["frame"]["offset_applied"],
                       "authority": snapshot["frame"]["authority"]}
    result["scored_excludes"] = ("construct failures, censored wells, and designs the batch "
                                 "carried no prediction for")
    return result


def _fmt(x):
    return "n/a" if x is None else "%.3f" % x
