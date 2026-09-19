#!/usr/bin/env python3
"""Verify the repo's invariants. Run after a fresh clone, and before trusting
any phase that builds on an earlier one.

    python check.py

Every check here corresponds to a rule in CLAUDE.md or a number recorded in
DECISIONS.md. A failure means the state has drifted from what is documented,
not that a test is being fussy.
"""

import ast
import math
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.abspath(__file__))
FAILS = []
TOTAL = 0


def check(label, ok, detail=""):
    global TOTAL
    TOTAL += 1
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", label, ("  -- " + detail) if detail else ""))
    if not ok:
        FAILS.append(label)
    return ok


def main():
    import numpy as np

    from core import acquisition, candidates, encode, project, reconcile, schema, surrogate
    from data import synthetic
    from data.oracle import Oracle, assay_version

    man = schema.read_json(os.path.join(REPO, "data", "landscape_manifest.json"))
    d = man["derived"]

    print("\nBoundaries (CLAUDE.md non-negotiables 1, 2, 4)")
    core_files = sorted(
        os.path.join(r, f)
        for r, _, fs in os.walk(os.path.join(REPO, "core"))
        for f in fs if f.endswith(".py"))
    imported, printing = set(), []
    for path in core_files:
        tree = ast.parse(open(path).read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "print":
                printing.append(os.path.basename(path))
    # Read the imports rather than grepping the prose: a module is allowed to
    # say in a comment that scipy is not a dependency.
    banned = {"scipy", "sklearn", "pandas", "matplotlib"}
    network = {"requests", "urllib", "socket", "http", "httpx"}
    check("core/ imports no simulated lab, no network",
          "data" not in imported and not (imported & network),
          "imports: %s" % ", ".join(sorted(imported)))
    check("core/ does not print", not printing, ", ".join(sorted(set(printing))))
    check("core/ uses no scipy, sklearn or pandas", not (imported & banned),
          "found %s" % sorted(imported & banned) if imported & banned else "numpy only")

    print("\nLandscape (DECISIONS.md pre-registered parameters)")
    out = subprocess.run([sys.executable, "-m", "data.build_oracle"], cwd=REPO,
                         capture_output=True, text=True)
    rebuilt = schema.read_json(os.path.join(REPO, "data", "landscape_manifest.json"))
    check("build is deterministic", rebuilt["build_hash"] == man["build_hash"], man["build_hash"][:19] + "...")
    check("realized linear R2 hits the 0.60 target",
          abs(d["realized_linear_r2"] - 0.60) < 0.01, "%.4f" % d["realized_linear_r2"])
    check("parent sits exactly at 9.000 pKD", abs(d["parent_pkd"] - 9.0) < 1e-9, "%.4f" % d["parent_pkd"])
    check("threshold is the recorded 10.762", abs(d["threshold_pkd"] - 10.762) < 0.001, "%.3f" % d["threshold_pkd"])
    check("detection limit is the recorded 6.861", abs(d["detection_limit_pkd"] - 6.861) < 0.001, "%.3f" % d["detection_limit_pkd"])
    check("cliff at VH 103, parent residue F",
          d["cliff_position"] == 103 and d["cliff_parent_residue"] == "F",
          "pos %d, parent %s, residues %s" % (d["cliff_position"], d["cliff_parent_residue"], d["cliff_residues"]))

    print("\nCandidate pool and constraints")
    tpl = schema.read_json(os.path.join(REPO, "templates", "antibody-affinity-maturation", "template.json"))
    parent, region = tpl["lead"]["sequence"], tpl["lead"]["editable_region"]
    pool = candidates.enumerate_variants(parent, region, tpl["constraints"]["max_mutations"])
    kept, removed = candidates.constraint_report(pool, parent, region, tpl["objectives"], tpl["constraints"])
    check("10,261 enumerated", len(pool) == 10261, str(len(pool)))
    check("7,294 feasible", len(kept) == 7294, "%d kept, %d removed %s" % (len(kept), len(removed), candidates.removal_summary(removed)))
    check("parent survives its own filter", parent in kept, "its inherited DG is not counted as introduced")
    check("editable window is GGDGFYAM", encode.window(parent, region) == "GGDGFYAM", encode.window(parent, region))

    print("\nGate conditions (must hold before phase 2 runs)")
    land = synthetic.Landscape(parent, region, synthetic.PARAMS)
    land.beta = d["beta"]
    v = land.value(kept)
    nmut = np.array([encode.n_mutations(parent, s, region) for s in kept])
    singles_max = float(v[nmut <= 1].max())
    above = int((v > d["threshold_pkd"]).sum())
    check("no single mutant can reach threshold", singles_max < d["threshold_pkd"],
          "best single %.3f < %.3f" % (singles_max, d["threshold_pkd"]))
    check("threshold is reachable but rare", 40 <= above <= 120,
          "%d of %d feasible (%.2f%%)" % (above, len(kept), 100.0 * above / len(kept)))

    print("\nProject instantiation (phase 1 done-condition)")
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, "init_project.py", "--name", "check", "--projects-dir", tmp],
                           cwd=REPO, capture_output=True, text=True)
        root = os.path.join(tmp, "check")
        ok = r.returncode == 0 and os.path.exists(os.path.join(root, "project.json"))
        check("a project is created from the template", ok, r.stderr.strip()[:80])
        if ok:
            st = project.load(root)
            designs = st["designs"]["designs"]
            check("round-1 designs written", len(designs) == 48, "%d designs" % len(designs))
            check("round 1 is a single-mutant scan",
                  all(x["n_mutations"] <= 1 for x in designs),
                  "max %d mutations" % max(x["n_mutations"] for x in designs))
            check("every record verifies against its own hash",
                  all(schema.verify(st[k]) for k in ("project", "objectives", "designs", "rounds")))

    print("\nSimulated lab")
    orc = Oracle(land, d["detection_limit_pkd"])
    check("assay version changes at round 4",
          assay_version(3) == "v1.2" and assay_version(4) == "v1.3",
          "r3 %s -> r4 %s" % (assay_version(3), assay_version(4)))
    check("round 4 carries the version shift",
          orc.round_offset(4) < -0.5 and abs(orc.round_offset(3)) < 0.3,
          "r3 %+.3f, r4 %+.3f" % (orc.round_offset(3), orc.round_offset(4)))
    rows = orc.measure(kept[:48], 1)
    check("replicates return as separate rows", len(rows) == 96, "%d rows for 48 designs" % len(rows))
    check("failures and censoring are representable",
          {"ok", "failed", "censored_low"} >= {r["status"] for r in rows})

    print("\nPhase 2: surrogates, acquisition, reconciliation")
    features = surrogate.Features(kept, region)
    check("the one-hot block and its PCA are the shapes they claim",
          features.X.shape == (7294, 160) and features.n_components == 64,
          "onehot %s, %d components holding %.0f%% of variance"
          % (features.X.shape, features.n_components, 100 * features.explained_variance_ratio))
    check("the error function matches the standard library",
          max(abs(float(a) - math.erf(float(b)))
              for a, b in zip(surrogate.erf(np.linspace(-4, 4, 33)), np.linspace(-4, 4, 33))) < 2e-7,
          "max abs error under 2e-7, and it is pure numpy so it agrees under WebAssembly")

    scan = candidates.round1_batch(kept, parent, region, 48, "single_mutant_scan")[0]
    covered = {i for s in scan for i in range(region[0], region[1]) if s[i] != parent[i]}
    check("the round-1 scan covers every editable position",
          covered == set(range(region[0], region[1])),
          "%d of %d positions, %d designs each"
          % (len(covered), region[1] - region[0], 48 // (region[1] - region[0])))

    rows = orc.measure(scan, 1, acquisition.assign_plates(scan, 1))
    agg = reconcile.aggregate_reads(rows)
    check("reads aggregate to one record per design",
          len(agg) == 48 and all(v["n_reads"] == 2 for v in agg.values()),
          "%d designs from %d rows" % (len(agg), len(rows)))

    obs = [{"sequence": s, "value": v["value"], "censored": v["censored"]}
           for s, v in agg.items() if v["value"] is not None]
    run = surrogate.fit_surrogates(features, obs)
    check("both registered recipes fit and are cross-validated",
          set(run["recipes"]) == {"ridge_onehot", "gp_pca64"}
          and all(np.isfinite(r["nlpd"]) for r in run["recipes"].values()),
          "winner %s on held-out nlpd  (%s)"
          % (run["winner"], ", ".join("%s %.2f" % (k, v["nlpd"])
                                      for k, v in sorted(run["recipes"].items()))))
    check("the winner is the recipe with the lowest held-out nlpd",
          run["winner"] == min(run["recipes"], key=lambda r: run["recipes"][r]["nlpd"]))
    check("predictions cover the whole feasible pool and are finite",
          run["pool_mean"].shape == (7294,) and np.isfinite(run["pool_mean"]).all()
          and (run["pool_sd"] > 0).all(),
          "mean %.2f to %.2f pKD, sd %.2f to %.2f"
          % (run["pool_mean"].min(), run["pool_mean"].max(),
             run["pool_sd"].min(), run["pool_sd"].max()))

    inc = max(o["value"] for o in obs)
    ei = acquisition.expected_improvement(run["pool_mean"], run["pool_sd"], inc)
    check("expected improvement is non-negative and rises with the mean",
          (ei >= 0).all() and ei[int(np.argmax(run["pool_mean"]))] > float(np.median(ei)),
          "max EI %.3f against an incumbent of %.3f" % (ei.max(), inc))

    pooled = reconcile.pool([dict(v, round=1) for v in agg.values()])
    batch = acquisition.compose_batch(
        features, tpl["batch"], parent=parent, observed=pooled, previous_batch=scan,
        mean=run["pool_mean"], sd=run["pool_sd"], incumbent=inc,
        objectives=tpl["objectives"], mode="guided")
    comp = batch["composition"]
    check("batch size is inclusive of its control, replicate and exploration slots",
          batch["size"] == 48 and comp == {"control": 2, "replicate": 2, "exploration": 2, "pick": 42},
          "48 wells = %s" % comp)
    check("the bridge excludes the design chosen for reading high",
          len(batch["bridge"]) == 3 and parent in batch["bridge"]
          and all(s["sequence"] not in batch["bridge"]
                  for s in batch["slots"] if s["slot"] == "control" and s["sequence"] != parent),
          "%d bridge designs: the parent and two spanning the previous batch" % len(batch["bridge"]))
    check("every fresh pick is new and inside the feasible pool",
          all(s not in pooled for s in batch["fresh"]) and all(s in kept for s in batch["sequences"]),
          "%d fresh, %d re-measured" % (len(batch["fresh"]), len(batch["re_measured"])))

    print("\nPhase 2: the round-4 offset is recoverable and flagged")
    camp = schema.read_json(os.path.join(REPO, "web", "public", "assets", "campaign.json"))
    guided = camp["runs"]["guided"]
    r4 = [run_[3] for run_ in guided]
    err = np.array([x["offset_estimated"] - x["offset_true"] for x in r4])
    bridge_n = [x["offset_bridge_n"] for x in r4]
    check("the bridging set recovers the round-4 offset",
          abs(err.mean()) < 0.15 and np.abs(err).max() < 0.40
          and min(bridge_n) >= 2 and sum(1 for n in bridge_n if n >= 3) >= 0.8 * len(r4),
          "estimated %+.3f against a true %+.3f, mean error %+.3f, worst %.3f; "
          "bridge of 3 in %d of %d runs and 2 in the rest, where a construct failed"
          % (np.mean([x["offset_estimated"] for x in r4]),
             np.mean([x["offset_true"] for x in r4]), err.mean(), np.abs(err).max(),
             sum(1 for n in bridge_n if n >= 3), len(r4)))

    # Round 4 is the standout, not the only one that ever fires. A round can
    # disagree with the model for honest reasons -- round 2 fits doubles from
    # a singles-only scan and comes back high -- and suppressing that to make
    # one round look special would be dressing up the flag.
    fired = {r: sum(1 for run_ in guided if run_[r - 1]["flagged"]) for r in (2, 3, 4, 5, 6)}
    mag = {r: float(np.median(np.abs([run_[r - 1]["mean_signed_residual"] for run_ in guided])))
           for r in (2, 3, 4, 5, 6)}
    check("round 4 flags on almost every seed",
          fired[4] >= 0.9 * len(guided),
          "flagged in %d of %d runs; the one that did not had a true offset of only "
          "%+.3f pKD" % (fired[4], len(guided),
                         min(x["offset_true"] for x in r4 if not x["flagged"])))
    check("round 4 stands out from every other round by a factor of two",
          all(mag[4] > 2.0 * mag[r] for r in (3, 5, 6)) and mag[4] > 1.5 * mag[2],
          "median |discrepancy| by round: %s"
          % ", ".join("r%d %.2f" % (r, mag[r]) for r in sorted(mag)))
    check("the rounds after the ruling go quiet",
          fired[6] <= 0.2 * len(guided) and fired[5] <= 0.4 * len(guided),
          "flagged in %s of %d runs" % (fired, len(guided)))
    check("a round on an assay version already characterized is not re-flagged",
          all(not run_[3]["assay_version_known"] and run_[4]["assay_version_known"]
              for run_ in guided),
          "v1.3 is unknown at round 4 and known at round 5")

    print("\nPhase 2 gate (SPEC.md acceptance criterion 1)")
    gate = camp["gate"]
    check("the campaign scored the pre-registered threshold on the built landscape",
          abs(camp["threshold_pkd"] - 10.762) < 0.001
          and camp["landscape_build_hash"] == man["build_hash"],
          "threshold %.3f, landscape %s" % (camp["threshold_pkd"], camp["landscape_build_hash"][:19] + "..."))
    check("20 seeds per arm over 6 rounds",
          camp["n_seeds"] == 20 and camp["n_rounds"] == 6
          and all(len(v) == 20 for v in camp["runs"].values()),
          "%d arms x %d seeds" % (len(camp["runs"]), camp["n_seeds"]))
    check("guided is never slower to threshold than random on any seed",
          gate["guided_never_slower"] and gate["guided_faster_on_more_seeds"],
          "%d faster, %d slower, p = %.4f, mean %.2f vs %.2f rounds"
          % (gate["paired_sign_test"]["wins"], gate["paired_sign_test"]["losses"],
             gate["paired_sign_test"]["p_value"], gate["mean_rounds_to_threshold"][0],
             gate["mean_rounds_to_threshold"][1]))
    check("the interquartile bands separate", gate["interquartile_bands_separate"],
          "at rounds %s" % gate["rounds_where_bands_separate"])
    check("GATE: guided separates from random", gate["passed"], gate["statement"][:58] + "...")

    if FAILS:
        print("\n%d of %d checks FAILED:" % (len(FAILS), TOTAL))
        for f in FAILS:
            print("  - %s" % f)
        print()
        return 1
    print("\nAll %d checks passed.\n" % TOTAL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
