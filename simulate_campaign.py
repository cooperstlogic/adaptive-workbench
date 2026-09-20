#!/usr/bin/env python3
"""The proof chart. Guided selection against random, over the same landscape.

    .venv/bin/python simulate_campaign.py
    .venv/bin/python simulate_campaign.py --seeds 3 --arms guided,random   # quick

This is the evaluator, not the product. It is the one and only thing in the
repository permitted to read landscape values, and it does so only to score
the diagnostic line -- the line that asks what each arm actually picked,
before the simulated assay added noise to the answer. Nothing on a product
path may do this.

The threshold it scores against was pre-registered (README.md, "Pre-registered
landscape parameters") and committed before this file first ran. If guided does not separate from
random, the deliverable is a sentence saying it did not.
"""

import argparse
import math
import os
import sys
import time

import numpy as np

from core import acquisition, candidates, encode, reconcile, schema, surrogate
from data import oracle as oracle_mod
from data import synthetic

REPO = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(REPO, "templates", "antibody-affinity-maturation", "template.json")
MANIFEST = os.path.join(REPO, "data", "landscape_manifest.json")
OUT = os.path.join(REPO, "web", "public", "assets", "campaign.json")

ARMS = {
    "guided": {"mode": "guided", "correct_offsets": True,
               "label": "model-guided, offsets corrected"},
    "random": {"mode": "random", "correct_offsets": True,
               "label": "random from the feasible pool"},
    "guided_naive": {"mode": "guided", "correct_offsets": False,
                     "label": "model-guided, measurements pooled naively"},
}
NOT_REACHED = None


# --- the campaign ----------------------------------------------------------


class Context:
    """Everything shared across every run: built once, never mutated."""

    def __init__(self, n_rounds):
        self.template = schema.read_json(TEMPLATE)
        self.manifest = schema.read_json(MANIFEST)
        derived = self.manifest["derived"]
        self.parent = self.template["lead"]["sequence"]
        self.region = self.template["lead"]["editable_region"]
        self.policy = self.template["batch"]
        self.objectives = self.template["objectives"]
        self.anomaly = self.template["anomaly_flag"]
        self.threshold = float(derived["threshold_pkd"])
        self.detection_limit = float(derived["detection_limit_pkd"])
        self.n_rounds = int(n_rounds)

        pool = candidates.enumerate_variants(
            self.parent, self.region, self.template["constraints"]["max_mutations"])
        self.feasible, removed = candidates.constraint_report(
            pool, self.parent, self.region, self.objectives, self.template["constraints"])
        self.n_enumerated, self.n_removed = len(pool), len(removed)
        self.features = surrogate.Features(self.feasible, self.region)

        self.seed_batch, self.seed_draw = candidates.round1_batch(
            self.feasible, self.parent, self.region, self.policy["size"],
            self.policy.get("round1_policy", "diversity"))

        # Ground truth. Read here and nowhere else.
        self.landscape = synthetic.Landscape(self.parent, self.region, synthetic.PARAMS)
        self.landscape.beta = derived["beta"]
        self.truth = dict(zip(self.feasible, self.landscape.value(self.feasible)))
        self.n_above = int(sum(1 for v in self.truth.values() if v > self.threshold))


def run_campaign(ctx, arm, run_seed):
    """One arm, one seed, ``ctx.n_rounds`` rounds. -> per-round records."""
    spec = ARMS[arm]
    orc = oracle_mod.Oracle(ctx.landscape, ctx.detection_limit, run_seed=run_seed)
    rng = np.random.default_rng((run_seed, 4242))

    records, rounds = [], []
    previous_batch, model_run = None, None
    selected = set()
    best_single = None
    base_offset = orc.round_offset(1)

    # What the project already knows about each assay version. Round 1 defines
    # the frame, so its version sits at zero by construction. A version first
    # seen in round N is, by definition, uncharacterized when round N lands --
    # which is exactly why that round is the one that needs a ruling, and why
    # the rounds after it do not: they are compared against a fact the project
    # has since recorded.
    known_offsets = {oracle_mod.assay_version(1): 0.0}

    for r in range(1, ctx.n_rounds + 1):
        pooled = reconcile.pool(records)
        incumbent = max((v["value"] for v in pooled.values()), default=None)

        if r == 1:
            batch = {"sequences": list(ctx.seed_batch), "bridge": [],
                     "fresh": list(ctx.seed_batch),
                     "composition": {"pick": len(ctx.seed_batch)},
                     "mode": "seed", "slots": []}
        else:
            mean = sd = None
            if spec["mode"] == "guided":
                obs = [{"sequence": s, "value": v["value"], "censored": v["censored"]}
                       for s, v in pooled.items()]
                model_run = surrogate.fit_surrogates(ctx.features, obs)
                mean, sd = model_run["pool_mean"], model_run["pool_sd"]
            batch = acquisition.compose_batch(
                ctx.features, ctx.policy, parent=ctx.parent, observed=pooled,
                previous_batch=previous_batch, mean=mean, sd=sd, incumbent=incumbent,
                objectives=ctx.objectives, mode=spec["mode"], rng=rng)

        sequences = batch["sequences"]
        selected.update(sequences)
        plates = acquisition.assign_plates(sequences, r)
        rows = orc.measure(sequences, r, plates)
        aggregated = reconcile.aggregate_reads(rows)

        # The anomaly flag is computed on what the lab returned, before any
        # correction -- which is the whole point: the flag is what tells you
        # something needs deciding.
        #
        # Scope matters: the statistic is computed over this round's *fresh*
        # designs only. The re-measured ones are the bridge, and letting the
        # bridge into the flag would mean the alert had already decided that
        # the run moved rather than that the designs are genuinely worse.
        version = oracle_mod.assay_version(r)
        known = known_offsets.get(version)
        flag = None
        if model_run is not None and batch["fresh"]:
            fresh = [s for s in batch["fresh"]
                     if aggregated[s]["value"] is not None and not aggregated[s]["censored"]]
            if fresh:
                mu, sg = surrogate.predict(model_run, ctx.features, fresh)
                got = np.array([aggregated[s]["value"] for s in fresh]) - (known or 0.0)
                flag = reconcile.anomaly_flag(got, mu, sg, ctx.anomaly)
                flag["assay_version"] = version
                flag["known_version_offset"] = known

        reference = {s: v["value"] for s, v in pooled.items() if not v["censored"]}
        estimate = reconcile.offset_from_bridge(aggregated, reference, designs=batch["bridge"])
        applied = estimate["offset"] if spec["correct_offsets"] else 0.0
        corrected = reconcile.apply_offset(aggregated, applied)
        for rec in corrected.values():
            rec["round"] = r
            records.append(rec)
        if version not in known_offsets:
            known_offsets[version] = applied

        merged = reconcile.pool(records)
        best_observed = max(v["value"] for v in merged.values())
        # The molecule this arm would actually advance: the design its own
        # project state ranks first. Scoring that pick at its landscape value
        # is the decision-relevant question, and it is a different question
        # from whether the reported number is right.
        nominated = max(merged, key=lambda s: merged[s]["value"])
        # Two readings of "best observed", and they differ where it matters.
        # ``best_observed`` is the project's current estimate for its best
        # design, so re-measuring a design can move it down -- which is
        # exactly what happens to an arm that pools across an assay version
        # change. ``best_single_observation`` is the running maximum over
        # individual corrected measurements, which is monotone by
        # construction. Both are reported so neither claim rests on the
        # choice of metric.
        round_best = max((rec["value"] for rec in corrected.values()
                          if rec["value"] is not None), default=None)
        if round_best is not None:
            best_single = round_best if best_single is None else max(best_single, round_best)
        best_landscape = max(ctx.truth[s] for s in selected)
        rounds.append({
            "round": r,
            "n_designs": len(sequences),
            "n_new": sum(1 for s in sequences if s not in pooled),
            "composition": batch["composition"],
            "assay_version": version,
            "assay_version_known": known is not None,
            "best_observed": float(best_observed),
            "best_single_observation": float(best_single),
            "nominated_true": float(ctx.truth[nominated]),
            "nominated_id": encode.sequence_id(nominated),
            "best_landscape": float(best_landscape),
            "n_measured": len(merged),
            "n_failed": sum(1 for s in sequences if aggregated[s]["status"] == "failed"),
            "n_censored": sum(1 for s in sequences if aggregated[s]["censored"]),
            "offset_estimated": float(estimate["offset"]),
            "offset_se": estimate["se"],
            "offset_bridge_n": estimate["n"],
            "offset_true": float(orc.round_offset(r) - base_offset),
            "offset_applied": float(applied),
            "flagged": None if flag is None else bool(flag["flagged"]),
            "mean_signed_residual": None if flag is None else float(flag["mean_signed_residual"]),
            "residual_z": None if flag is None else flag["z"],
            "outside_interval": None if flag is None else float(flag["outside_interval"]),
            "winner": None if model_run is None else model_run["winner"],
            "cv": None if model_run is None else {
                k: {"rmse": v["rmse"], "r2": v["r2"], "coverage_80": v["coverage_80"],
                    "nlpd": v["nlpd"]}
                for k, v in model_run["recipes"].items()},
        })
        previous_batch = sequences

    return rounds


# --- statistics ------------------------------------------------------------


def quantiles(values):
    a = np.asarray(values, dtype=np.float64)
    return {"q1": float(np.percentile(a, 25)), "median": float(np.median(a)),
            "q3": float(np.percentile(a, 75)), "min": float(a.min()), "max": float(a.max())}


def rounds_to_threshold(rounds, threshold, key="best_observed", cap=None):
    for rec in rounds:
        if rec[key] >= threshold:
            return rec["round"]
    return cap


def sign_test(a, b):
    """Exact two-sided paired sign test. Pure stdlib; scipy is not a dependency.

    ``a`` better than ``b`` means a smaller value, so this is used on
    rounds-to-threshold directly and on negated pKD elsewhere.
    """
    wins = sum(1 for x, y in zip(a, b) if x < y)
    losses = sum(1 for x, y in zip(a, b) if x > y)
    n = wins + losses
    if n == 0:
        return {"wins": 0, "losses": 0, "ties": len(a), "p_value": 1.0}
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2.0 ** n)
    return {"wins": wins, "losses": losses, "ties": len(a) - n,
            "p_value": float(min(1.0, 2.0 * tail))}


def summarize(ctx, results):
    cap = ctx.n_rounds + 1
    summary = {}
    for arm, runs in results.items():
        per_round = []
        for r in range(1, ctx.n_rounds + 1):
            obs = [run[r - 1]["best_observed"] for run in runs]
            land = [run[r - 1]["best_landscape"] for run in runs]
            per_round.append({
                "round": r,
                "best_observed": quantiles(obs),
                "best_single_observation": quantiles([run[r - 1]["best_single_observation"] for run in runs]),
                "nominated_true": quantiles([run[r - 1]["nominated_true"] for run in runs]),
                "best_landscape": quantiles(land),
                "reached_threshold": float(np.mean([v >= ctx.threshold for v in obs])),
                "reached_threshold_landscape": float(np.mean([v >= ctx.threshold for v in land])),
            })
        rtt = [rounds_to_threshold(run, ctx.threshold, cap=cap) for run in runs]
        rtt_land = [rounds_to_threshold(run, ctx.threshold, "best_landscape", cap=cap) for run in runs]
        summary[arm] = {
            "label": ARMS[arm]["label"],
            "n_runs": len(runs),
            "per_round": per_round,
            "rounds_to_threshold": rtt,
            "rounds_to_threshold_landscape": rtt_land,
            "median_rounds_to_threshold": float(np.median(rtt)),
            "mean_rounds_to_threshold": float(np.mean(rtt)),
            "median_rounds_to_threshold_landscape": float(np.median(rtt_land)),
            "mean_rounds_to_threshold_landscape": float(np.mean(rtt_land)),
            "reached_by_final_round": float(np.mean([v <= ctx.n_rounds for v in rtt])),
            "final_best_observed": quantiles([run[-1]["best_observed"] for run in runs]),
            "final_best_landscape": quantiles([run[-1]["best_landscape"] for run in runs]),
        }
    return summary


def compare(ctx, summary, a, b):
    cap = ctx.n_rounds + 1
    ra, rb = summary[a]["rounds_to_threshold"], summary[b]["rounds_to_threshold"]
    bands = []
    for i in range(ctx.n_rounds):
        pa, pb = summary[a]["per_round"][i], summary[b]["per_round"][i]
        bands.append({
            "round": i + 1,
            "separated_observed": bool(pa["best_observed"]["q1"] > pb["best_observed"]["q3"]),
            "separated_landscape": bool(pa["best_landscape"]["q1"] > pb["best_landscape"]["q3"]),
        })
    return {
        "arms": [a, b],
        "rounds_to_threshold": {
            "median": [summary[a]["median_rounds_to_threshold"],
                       summary[b]["median_rounds_to_threshold"]],
            "mean": [summary[a]["mean_rounds_to_threshold"],
                     summary[b]["mean_rounds_to_threshold"]],
            "delta": summary[b]["mean_rounds_to_threshold"] - summary[a]["mean_rounds_to_threshold"],
            "never_slower": bool(all(x <= y for x, y in zip(ra, rb))),
            "sign_test": sign_test(ra, rb),
            "note": "runs that never reached the threshold are recorded as %d" % cap,
        },
        "band_separation": bands,
        "rounds_separated_observed": [x["round"] for x in bands if x["separated_observed"]],
        "rounds_separated_landscape": [x["round"] for x in bands if x["separated_landscape"]],
    }


def paired_final(results, a, b, key="best_observed"):
    xa = [run[-1][key] for run in results[a]]
    xb = [run[-1][key] for run in results[b]]
    return {
        "metric": key,
        "median_delta": float(np.median(xa) - np.median(xb)),
        "wins": int(sum(1 for x, y in zip(xa, xb) if x > y)),
        "sign_test": sign_test([-v for v in xa], [-v for v in xb]),
    }


# --- reporting -------------------------------------------------------------


MARKS = {"guided": "G", "random": "R", "guided_naive": "N"}


def ascii_chart(ctx, summary, arms, key="best_observed", height=16):
    lows = [summary[a]["per_round"][0][key]["min"] for a in arms]
    highs = [summary[a]["per_round"][-1][key]["max"] for a in arms]
    lo, hi = min(lows) - 0.05, max(highs + [ctx.threshold]) + 0.05
    span = max(hi - lo, 1e-6)
    grid = [[" "] * (ctx.n_rounds * 6) for _ in range(height)]

    def row(v):
        return int(round((hi - v) / span * (height - 1)))

    trow = row(ctx.threshold)
    if 0 <= trow < height:
        grid[trow] = ["-"] * (ctx.n_rounds * 6)
    for a in arms:
        for i, rec in enumerate(summary[a]["per_round"]):
            col = i * 6 + 2
            q = rec[key]
            top, bot = row(q["q3"]), row(q["q1"])
            for rr in range(min(top, bot), max(top, bot) + 1):
                if 0 <= rr < height and grid[rr][col] == " ":
                    grid[rr][col] = ":"
            mr = row(q["median"])
            if 0 <= mr < height:
                grid[mr][col] = MARKS[a]

    lines = []
    for i, line in enumerate(grid):
        v = hi - (i / (height - 1)) * span
        tag = " <- threshold %.3f" % ctx.threshold if i == trow else ""
        lines.append("  %7.3f |%s%s" % (v, "".join(line).rstrip(), tag))
    lines.append("          +" + "-" * (ctx.n_rounds * 6))
    lines.append("           " + "".join("  R%-4d" % (i + 1) for i in range(ctx.n_rounds)))
    return "\n".join(lines)


def report(ctx, summary, comparisons, arms, elapsed):
    out = []
    w = out.append
    w("")
    w("=" * 76)
    w("PROOF CHART  --  cumulative best observed pKD, median with interquartile band")
    w("=" * 76)
    w("  SYNTHETIC LANDSCAPE. This shows the loop converges. It does not show that")
    w("  the method finds better antibodies.")
    w("")
    w("  threshold %.3f pKD, pre-registered as the 99th percentile before any run"
      % ctx.threshold)
    w("  %d of %d feasible designs are above it (%.2f%%)"
      % (ctx.n_above, len(ctx.feasible), 100.0 * ctx.n_above / len(ctx.feasible)))
    w("  %d seeds per arm, %d rounds, batch of %d, shared round-1 single-mutant scan"
      % (summary[arms[0]]["n_runs"], ctx.n_rounds, ctx.policy["size"]))
    w("")
    w(ascii_chart(ctx, summary, arms))
    w("")
    w("  " + "   ".join("%s = %s" % (MARKS[a], ARMS[a]["label"]) for a in arms))
    w("")
    w("-" * 76)
    w("Cumulative best observed pKD (median [q1, q3])")
    w("-" * 76)
    w("  round  " + "  ".join("%-24s" % a for a in arms))
    for i in range(ctx.n_rounds):
        cells = []
        for a in arms:
            q = summary[a]["per_round"][i]["best_observed"]
            cells.append("%-24s" % ("%6.3f [%6.3f %6.3f]" % (q["median"], q["q1"], q["q3"])))
        w("  %-5d  " % (i + 1) + "  ".join(cells))
    w("")
    w("Cumulative best landscape pKD over selections (diagnostic line, noise-free)")
    w("-" * 76)
    w("  round  " + "  ".join("%-24s" % a for a in arms))
    for i in range(ctx.n_rounds):
        cells = []
        for a in arms:
            q = summary[a]["per_round"][i]["best_landscape"]
            cells.append("%-24s" % ("%6.3f [%6.3f %6.3f]" % (q["median"], q["q1"], q["q3"])))
        w("  %-5d  " % (i + 1) + "  ".join(cells))
    w("")
    w("-" * 76)
    w("Rounds to threshold  (never reached is recorded as %d)" % (ctx.n_rounds + 1))
    w("-" * 76)
    for a in arms:
        s = summary[a]
        w("  %-14s median %4.1f   reached by round %d in %d of %d runs"
          % (a, s["median_rounds_to_threshold"], ctx.n_rounds,
             int(round(s["reached_by_final_round"] * s["n_runs"])), s["n_runs"]))
    w("")
    for c in comparisons:
        a, b = c["arms"]
        rt = c["rounds_to_threshold"]
        st = rt["sign_test"]
        w("  %s vs %s" % (a, b))
        w("    rounds to threshold   mean %.2f vs %.2f (%+.2f)   median %.1f vs %.1f%s"
          % (rt["mean"][0], rt["mean"][1], -rt["delta"], rt["median"][0], rt["median"][1],
             "  (median ties: a count with a floor at 2)"
             if rt["median"][0] == rt["median"][1] else ""))
        w("    paired sign test over seeds  %d wins / %d losses / %d ties, p = %.4f%s"
          % (st["wins"], st["losses"], st["ties"], st["p_value"],
             "   never slower on any seed" if rt["never_slower"] else ""))
        w("    interquartile bands separate at rounds  observed %s   landscape %s"
          % (c["rounds_separated_observed"] or "none", c["rounds_separated_landscape"] or "none"))
        w("    final best observed, median delta  %+.3f pKD  (%d of %d seeds ahead)"
          % (c["final"]["median_delta"], c["final"]["wins"], summary[a]["n_runs"]))
        w("")
    w("  ran in %.1f s" % elapsed)
    w("=" * 76)
    return "\n".join(out)


def gate_verdict(ctx, summary, comparison):
    """The hour-3 gate, stated as a pass or a failure and nothing in between.

    The criterion is the one written down before any of this ran:
    guided reaches the pre-registered threshold in measurably fewer rounds
    than random over twenty seeds per arm, and the interquartile bands
    separate. Because the twenty runs are paired -- same landscape, same
    round-1 batch, same assay draws, one arm differing -- the measurement is
    the paired comparison across those seeds.

    The median of rounds-to-threshold is reported and is deliberately not the
    test. It is a discrete count with a floor at two, guided lands on that
    floor in most seeds, and it ties at 2.0 for both arms while guided is
    never once slower. A statistic with no resolution is not evidence either
    way, and reading a tie there as a failure would be as wrong as reading it
    as a pass.
    """
    rt = comparison["rounds_to_threshold"]
    st = rt["sign_test"]
    faster = st["wins"] > st["losses"]
    never_slower = bool(rt["never_slower"])
    significant = st["p_value"] < 0.05
    separated = bool(comparison["rounds_separated_observed"])
    passed = bool(faster and significant and separated)
    return {
        "passed": passed,
        "criterion": ("guided reaches the pre-registered threshold in measurably fewer "
                      "rounds than random over 20 paired seeds, and the interquartile "
                      "bands separate"),
        "guided_faster_on_more_seeds": bool(faster),
        "guided_never_slower": never_slower,
        "paired_sign_test": st,
        "sign_test_significant_at_0.05": bool(significant),
        "mean_rounds_to_threshold": rt["mean"],
        "median_rounds_to_threshold": rt["median"],
        "median_has_no_resolution": bool(rt["median"][0] == rt["median"][1]),
        "interquartile_bands_separate": separated,
        "rounds_where_bands_separate": comparison["rounds_separated_observed"],
        "statement": (
            "GATE PASSED: guided selection reaches the pre-registered threshold in "
            "fewer rounds than random over 20 paired seeds, and the interquartile "
            "bands separate. The landscape is synthetic, so this shows the loop "
            "converges and not that the method finds better antibodies."
            if passed else
            "GATE NOT PASSED: guided selection did not separate from random on this "
            "landscape. The landscape and the threshold stay as they are."
        ),
    }


# --- entry point -----------------------------------------------------------


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=20, help="independent runs per arm")
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--arms", default="guided,random,guided_naive")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    for a in arms:
        if a not in ARMS:
            print("unknown arm %r; choose from %s" % (a, ", ".join(ARMS)), file=sys.stderr)
            return 2

    started = time.time()
    ctx = Context(args.rounds)
    if not args.quiet:
        print("landscape      %s" % ctx.manifest["build_hash"][:26] + "...")
        print("feasible pool  %d designs, %d above the threshold (%.2f%%)"
              % (len(ctx.feasible), ctx.n_above, 100.0 * ctx.n_above / len(ctx.feasible)))
        print("pca            %d components, %.1f%% of one-hot variance"
              % (ctx.features.n_components, 100.0 * ctx.features.explained_variance_ratio))
        print("running        %d arms x %d seeds x %d rounds" % (len(arms), args.seeds, args.rounds))

    results = {}
    for arm in arms:
        runs = []
        for seed in range(args.seeds):
            t0 = time.time()
            runs.append(run_campaign(ctx, arm, seed))
            if not args.quiet:
                print("  %-13s seed %2d  best %.3f  %4.1fs"
                      % (arm, seed, runs[-1][-1]["best_observed"], time.time() - t0),
                      flush=True)
        results[arm] = runs

    summary = summarize(ctx, results)
    comparisons = []
    if "guided" in results and "random" in results:
        c = compare(ctx, summary, "guided", "random")
        c["final"] = paired_final(results, "guided", "random")
        comparisons.append(c)
    if "guided" in results and "guided_naive" in results:
        c = compare(ctx, summary, "guided", "guided_naive")
        c["final"] = paired_final(results, "guided", "guided_naive")
        c["final_landscape"] = paired_final(results, "guided", "guided_naive", "best_landscape")
        comparisons.append(c)

    elapsed = time.time() - started
    verdict = gate_verdict(ctx, summary, comparisons[0]) if comparisons else None

    payload = {
        "schema_version": schema.SCHEMA_VERSION,
        "kind": "campaign_comparison",
        "synthetic": True,
        "synthetic_note": ("The landscape is invented. This chart shows that the decision "
                           "loop converges; it does not show that the method finds better "
                           "antibodies."),
        "unit": schema.UNIT,
        "landscape_build_hash": ctx.manifest["build_hash"],
        "threshold_pkd": ctx.threshold,
        "threshold_provenance": ("99th percentile of the landscape, pre-registered and "
                                 "committed before any campaign ran"),
        "detection_limit_pkd": ctx.detection_limit,
        "n_seeds": args.seeds,
        "n_rounds": args.rounds,
        "batch": ctx.policy,
        "feasible_pool": len(ctx.feasible),
        "above_threshold": ctx.n_above,
        "arms": {a: ARMS[a] for a in arms},
        "summary": summary,
        "comparisons": comparisons,
        "gate": verdict,
        "runs": results,
        "elapsed_seconds": elapsed,
    }
    payload["hash"] = schema.content_hash({k: v for k, v in payload.items() if k != "hash"})

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    schema.write_json(args.out, payload)

    try:
        import plot_campaign
        charts = plot_campaign.render_all(payload)
    except ImportError as exc:  # matplotlib is an evaluator dependency, not a hard one
        charts = []
        print("chart not rendered (%s); the numbers are still in campaign.json" % exc,
              file=sys.stderr)

    print(report(ctx, summary, comparisons, arms, elapsed))
    if verdict:
        print()
        print(verdict["statement"])
    print("\nwrote %s" % os.path.relpath(args.out, REPO))
    for path in charts:
        print("wrote %s" % os.path.relpath(path, REPO))
    return 0 if (verdict is None or verdict["passed"]) else 1


if __name__ == "__main__":
    sys.exit(main())
