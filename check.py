#!/usr/bin/env python3
"""Verify the repo's invariants. Run after a fresh clone, and before trusting
any phase that builds on an earlier one.

    python check.py

Every check here corresponds to a rule in CLAUDE.md or a number recorded in
DECISIONS.md. A failure means the state has drifted from what is documented,
not that a test is being fussy.
"""

import ast
import hashlib
import json
import math
import os
import shutil
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


def mcp_session(script):
    """Talk to a connector the way a client does: spawn it, speak the protocol.

    check.py drives the connectors over stdio rather than importing them,
    because stdio is the interface a host actually uses. Importing would test
    the Python and skip the transport, and the transport is the thing phase 5
    added.
    """
    import asyncio

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run(calls):
        params = StdioServerParameters(
            command=os.path.join(REPO, ".venv", "bin", "python"),
            args=[os.path.join(REPO, "connectors", script)], cwd=REPO)
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                init = await session.initialize()
                listed = await session.list_tools()
                out = {"server": init.server_info.name,
                       "tools": sorted(t.name for t in listed.tools),
                       "results": []}
                for name, args in calls:
                    res = await session.call_tool(name, args)
                    text = res.content[0].text if res.content else ""
                    out["results"].append({
                        "tool": name, "error": bool(res.is_error), "text": text,
                        "data": (json.loads(text)
                                 if not res.is_error and text.startswith("{") else None)})
                return out

    return lambda calls: asyncio.run(_run(calls))


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
            check("instantiation writes no designs and no pool",
                  not st["designs"]["designs"] and not st["rounds"]["rounds"]
                  and not os.listdir(os.path.join(root, "candidates")),
                  "round 1 goes through generate_candidates and select_batch like every "
                  "other round")
            check("the template's constraints and recipes are copied into the project",
                  st["objectives"]["constraints"]["max_mutations"] == 2
                  and st["objectives"]["model_recipes"] == list(surrogate.RECIPES),
                  ", ".join(st["objectives"]["model_recipes"]))
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

    print("\nPhase 2: what naive pooling actually costs")
    g6 = [run_[5]["nominated_true"] for run_ in guided]
    n6 = [run_[5]["nominated_true"] for run_ in camp["runs"]["guided_naive"]]
    worse = [a - b for a, b in zip(g6, n6) if b < a - 1e-9]
    check("naive pooling makes you advance a worse molecule, not just misreport one",
          len(worse) >= len(g6) // 2 and np.median(worse) > 0.3,
          "in %d of %d seeds, median %.3f pKD worse at round 6"
          % (len(worse), len(g6), np.median(worse)))
    check("guided holds the feasible pool's best design once it finds it",
          all(run_[5]["nominated_true"] >= run_[3]["nominated_true"] - 1e-9 for run_ in guided),
          "median nominated %.3f against a pool maximum of %.3f"
          % (np.median(g6), max(v for v in [float(np.max(land.value(kept)))])))
    check("the uncorrected arm keeps raising alerts it never resolves",
          sum(1 for r in camp["runs"]["guided_naive"] if r[4]["flagged"])
          > sum(1 for r in guided if r[4]["flagged"]),
          "round 5 flagged in %d of 20 naive runs against %d of 20 corrected"
          % (sum(1 for r in camp["runs"]["guided_naive"] if r[4]["flagged"]),
             sum(1 for r in guided if r[4]["flagged"])))

    assets = os.path.join(REPO, "web", "public", "assets")
    charts = ["campaign.png", "campaign.svg", "campaign-dark.png", "campaign-dark.svg"]
    check("the proof chart is rendered in both modes",
          all(os.path.getsize(os.path.join(assets, c)) > 20000 for c in charts),
          ", ".join("%s %dkB" % (c, os.path.getsize(os.path.join(assets, c)) // 1024)
                    for c in charts))

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

    print("\nPhase 3: boundaries of the pipeline scripts and the skill")
    skill_dir = os.path.join(REPO, "skills", "adaptive-optimization")
    scripts_dir = os.path.join(skill_dir, "scripts")
    expected = ["evaluate_prior.py", "fit_surrogates.py", "generate_candidates.py",
                "import_round.py", "record_decision.py", "run_diagnostic.py",
                "select_batch.py"]
    present = sorted(f for f in os.listdir(scripts_dir) if f.endswith(".py"))
    check("the five pipeline scripts and the two diagnosis scripts are present",
          present == expected, ", ".join(present))

    # Same method as the core boundary check above: read the imports rather than
    # grep the prose, because a docstring is allowed to name the oracle.
    leaked, banned_pkgs = {}, {"scipy", "sklearn", "pandas"}
    for name in present:
        path = os.path.join(scripts_dir, name)
        names = set()
        for node in ast.walk(ast.parse(open(path).read(), filename=path)):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        bad = {n for n in names
               if n.split(".")[0] in ({"data", "lims"} | banned_pkgs)}
        if bad:
            leaked[name] = sorted(bad)
    check("no pipeline script imports the simulated lab or the LIMS",
          not leaked, str(leaked) if leaked else
          "the workbench sees only what a lab reported, never ground truth")

    lims_src = open(os.path.join(REPO, "lims.py")).read()
    lims_imports = set()
    for node in ast.walk(ast.parse(lims_src)):
        if isinstance(node, ast.ImportFrom) and node.module:
            lims_imports.add(node.module)
    check("the oracle lives behind the LIMS, which is where core/ cannot reach it",
          "data.oracle" in lims_imports or "data" in lims_imports,
          "lims.py imports %s" % ", ".join(sorted(i for i in lims_imports if i.startswith("data"))))

    skill_md = open(os.path.join(skill_dir, "SKILL.md")).read()
    check("SKILL.md declares the skill name and a description that fires on the domain",
          skill_md.startswith("---\nname: adaptive-optimization\n")
          and "lead optimization" in skill_md and "batch selection" in skill_md)
    rules = ["Never change objectives without explicit approval",
             "Never pool measurements across assay versions without a bridging set",
             "Never invent a model recipe outside the registry",
             "Never write a number into a decision record that did not come from a named"]
    flat = " ".join(skill_md.split())
    check("SKILL.md carries all four rules the agent may not break",
          all(r in flat for r in rules),
          "%d of 4 present" % sum(1 for r in rules if r in flat))
    check("SKILL.md no longer labels anything in the round loop as unbuilt",
          "**Not built yet**" not in skill_md and "Do not simulate them." not in skill_md,
          "the two diagnosis scripts landed in phase 4")

    print("\nPhase 3: six rounds through the CLI (phase 3 done-condition)")
    camp_naive = camp["runs"]["guided_naive"][0]
    camp_guided = camp["runs"]["guided"][0]

    def cli_run(tmp, name, offset):
        """One full campaign through the CLI scripts, as subprocesses."""
        store = os.path.join(tmp, "store.json")
        r = subprocess.run([sys.executable, "init_project.py", "--name", name,
                            "--projects-dir", tmp], cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            return None, r.stderr
        r = subprocess.run([sys.executable, "run_rounds.py",
                            "--project", os.path.join(tmp, name), "--rounds", "6",
                            "--ignore-flags", "--offset", offset,
                            "--approved-by", "check.py",
                            "--results-dir", os.path.join(tmp, "exports"),
                            "--lims-store", store],
                           cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            return None, (r.stderr or r.stdout)[-300:]
        return project.load(os.path.join(tmp, name)), ""

    with tempfile.TemporaryDirectory() as tmp:
        st, err = cli_run(tmp, "cli", "never")
        check("six rounds run end to end through the five scripts and the LIMS",
              st is not None, err)
        if st is not None:
            entries = st["rounds"]["rounds"]
            check("rounds.json links every round's pool, batch, snapshot, evaluation and model",
                  len(entries) == 6 and all(
                      all(k in e for k in ("pool", "batch", "snapshot", "evaluation", "model"))
                      for e in entries),
                  "%d rounds, %d fully linked"
                  % (len(entries), sum(1 for e in entries if len(e) >= 7)))
            refs = [(e[k]["file"], e[k]["hash"]) for e in entries
                    for k in ("pool", "batch", "snapshot", "evaluation", "model")]
            mismatched = [f for f, h in refs
                          if schema.read_json(os.path.join(st["paths"]["root"], f))["hash"] != h]
            check("every hash in the round graph matches the record it points at",
                  not mismatched, "%d artifacts checked" % len(refs))
            bad = [f for f, _ in refs
                   if not schema.verify(schema.read_json(os.path.join(st["paths"]["root"], f)))]
            check("every artifact verifies against its own content hash", not bad,
                  "%d artifacts recomputed" % len(refs))

            b1 = project.read_artifact(st, "batches", 1)
            designs = {x["design_id"]: x for x in st["designs"]["designs"]}
            check("round 1 is a 48-design single-mutant scan chosen without a model",
                  len(b1["approved"]) == 48 and b1["mode"] == "seed"
                  and all(designs[x]["n_mutations"] <= 1 for x in b1["approved"]),
                  "%s, max %d mutations" % (b1["round1_policy"],
                                            max(designs[x]["n_mutations"]
                                                for x in b1["approved"])))
            b2 = project.read_artifact(st, "batches", 2)
            c2 = b2["composition"]
            check("batch size stays inclusive of its control, replicate and exploration slots",
                  len(b2["approved"]) == 48 and (c2["control"], c2["replicate"],
                                                 c2["exploration"], c2["pick"]) == (2, 2, 2, 42),
                  "48 wells = %d control, %d replicate, %d exploration, %d picks"
                  % (c2["control"], c2["replicate"], c2["exploration"], c2["pick"]))
            samples = {r["sample_id"] for r in st["designs"]["external_refs"]}
            ids = set(designs)
            check("the registry's sample ids are never design ids",
                  not (samples & ids) and len(samples) == 288,
                  "%d samples over six rounds, joined through the reference table"
                  % len(samples))
            prints = {project.read_artifact(st, "candidates", r)["pool_fingerprint"]
                      for r in range(1, 7)}
            check("the candidate pool hashes to the same value in all six rounds",
                  len(prints) == 1, schema.short_hash(prints.pop()))

            snap4 = project.read_artifact(st, "evidence", 4)
            check("round 4 flags and its frame does not move without a ruling",
                  snap4["flagged"] and snap4["frame"]["offset_applied"] == 0.0
                  and snap4["frame"]["authority"] == "unruled",
                  "estimate %+.3f recorded, applied %+.3f, authority %r"
                  % (snap4["frame"]["offset_estimate"]["offset"],
                     snap4["frame"]["offset_applied"], snap4["frame"]["authority"]))

            worst_b = worst_o = 0.0
            for r in range(1, 7):
                pooled = reconcile.pool(project.measurement_records(st, through=r))
                snap = project.read_artifact(st, "evidence", r)
                ref = camp_naive[r - 1]
                worst_b = max(worst_b, abs(max(v["value"] for v in pooled.values())
                                           - ref["best_observed"]))
                worst_o = max(worst_o, abs(snap["frame"]["offset_estimate"]["offset"]
                                           - ref["offset_estimated"]))
            check("GATE: the CLI reproduces the evaluator's uncorrected arm to file precision",
                  worst_b < 5e-6 and worst_o < 5e-6,
                  "worst best-observed delta %.0e, worst offset delta %.0e over six rounds"
                  % (worst_b, worst_o))

    with tempfile.TemporaryDirectory() as tmp:
        st, err = cli_run(tmp, "cli", "always")
        check("the same six rounds run with every round corrected from its bridge",
              st is not None, err)
        if st is not None:
            worst_b = 0.0
            for r in range(1, 7):
                pooled = reconcile.pool(project.measurement_records(st, through=r))
                worst_b = max(worst_b, abs(max(v["value"] for v in pooled.values())
                                           - camp_guided[r - 1]["best_observed"]))
            check("GATE: the CLI reproduces the evaluator's corrected arm to file precision",
                  worst_b < 5e-6,
                  "worst best-observed delta %.0e; the CLI and the evaluator select the same "
                  "288 wells" % worst_b)
            quiet = [project.read_artifact(st, "evidence", r)["flagged"] for r in (5, 6)]
            check("correcting round 4 makes the rounds after it go quiet", not any(quiet),
                  "rounds 5 and 6 flagged: %s" % quiet)

    print("\nPhase 3: the committed demo project")
    demo = project.load(os.path.join(REPO, "projects", "demo-trastuzumab"))
    entries = demo["rounds"]["rounds"]
    check("the demo project is committed at four rounds", len(entries) == 4,
          "rounds %s" % [e["round"] for e in entries])
    check("its batches carry a named approver",
          all(project.read_artifact(demo, "batches", e["round"])["approval"]["by"]
              == "d.webster" for e in entries),
          "the system proposes and a named person disposes")
    snap4 = project.read_artifact(demo, "evidence", 4)
    bridge = snap4["frame"]["offset_estimate"]
    check("round 4 comes back flagged and unruled",
          snap4["flagged"] and snap4["frame"]["authority"] == "unruled",
          "mean signed residual %+.3f pKD over %d fresh designs"
          % (snap4["anomaly"]["mean_signed_residual"], snap4["anomaly"]["n_compared"]))
    check("round 4 is genuinely ambiguous rather than a bare offset",
          bridge["n"] >= 3 and bridge["se"] is not None
          and abs(bridge["offset"] - snap4["anomaly"]["mean_signed_residual"]) > 0.5,
          "the bridge recovers %+.3f (se %.3f) while the fresh designs sit %+.3f -- an "
          "offset alone does not account for the round"
          % (bridge["offset"], bridge["se"], snap4["anomaly"]["mean_signed_residual"]))
    eval4 = project.read_artifact(demo, "batches", 4, suffix=".eval")
    check("the calibration collapse is recorded against the held-out estimate",
          eval4["calibration"]["realized_coverage"] < 0.2
          and eval4["calibration"]["drift_from_held_out"] < -0.5,
          "coverage %.2f realized against %.2f held out at fit time"
          % (eval4["calibration"]["realized_coverage"],
             eval4["calibration"]["held_out_coverage_at_fit"]))
    check("the unruled round is visible to the next fit rather than silently pooled",
          project.read_artifact(demo, "models", 4) is None
          and project.unruled_flagged_rounds(demo) == [4],
          "round 4 has no model run at all: the loop stopped before fitting it, which is "
          "what a flagged round is supposed to do")

    print("\nPhase 4: the diagnostics, and the decision record")
    from core import diagnostics

    scripts = os.path.join(REPO, "skills", "adaptive-optimization", "scripts")

    def cli(script, *args, **kw):
        return subprocess.run([sys.executable, os.path.join(scripts, script)] + list(args),
                              cwd=REPO, capture_output=True, text=True, **kw)

    def tree_hash(root):
        """Every byte under a project directory, so 'writes nothing' is checked."""
        out = {}
        for r, _, fs in os.walk(root):
            for f in sorted(fs):
                p = os.path.join(r, f)
                out[os.path.relpath(p, root)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        return out

    demo_root = demo["paths"]["root"]
    check("the template permits exactly the five diagnostics the library implements",
          tuple(demo["objectives"]["diagnostics"]) == diagnostics.TESTS,
          ", ".join(diagnostics.TESTS))
    check("the template declares the tolerances the tests measure against",
          all(k in demo["objectives"]["diagnostics_policy"] for k in diagnostics.DEFAULT_POLICY),
          "declared ahead of any conversation, not chosen while reading a round")

    before = tree_hash(demo_root)
    results, failed = {}, []
    for test in diagnostics.TESTS:
        r = cli("run_diagnostic.py", "--project", demo_root, "--round", "4", "--test", test)
        if r.returncode != 0:
            failed.append("%s: %s" % (test, r.stderr.strip()[-120:]))
            continue
        results[test] = json.loads(r.stdout)["result"]
    check("PHASE 4 DONE-CONDITION: all five tests return a number on the round-4 snapshot",
          not failed and len(results) == 5, "; ".join(failed) or "five for five")
    check("run_diagnostic.py writes nothing", tree_hash(demo_root) == before,
          "reading a round is not a decision, so nothing about the project changed")

    if len(results) == 5:
        off = results["offset_from_controls"]
        cal = results["calibration_by_region"]
        plate = results["residual_by_plate"]
        rep = results["replicate_concordance"]
        finite = all(isinstance(v, float) and math.isfinite(v) for v in
                     (off["offset_pkd"], off["se"], off["delta_sd"], cal["coverage"],
                      plate["max_gap"], rep["read_noise_scale"]))
        check("the numbers they return are finite and carry their own scale", finite,
              "offset %+.3f se %.3f, coverage %.2f, plate gap %.3f, noise scale %.3f"
              % (off["offset_pkd"], off["se"], cal["coverage"], plate["max_gap"],
                 rep["read_noise_scale"]))
        check("the bridge members agree, so the round has a correction available at all",
              off["concordant"] is True and off["n_bridge"] >= 3,
              "%d designs, spread sd %.3f inside a tolerance of %.3f"
              % (off["n_bridge"], off["delta_sd"], off["concordance_tolerance"]))
        check("the plates do not separate, so round 4 is not a plate artifact",
              abs(plate["z_of_gap"]) < 2.0,
              "gap %+.3f pKD, %.2f standard errors" % (plate["max_gap"], plate["z_of_gap"]))
        check("no construct's replicates disagree, so round 4 is not an unstable read",
              rep["n_flagged"] == 0,
              "%d designs with two reads, none above %.3f"
              % (rep["n_with_replicates"], rep["tolerance"]))

        r = cli("run_diagnostic.py", "--project", demo_root, "--round", "4",
                "--test", "residual_by_mutation_class", "--scope", "fresh")
        classes = json.loads(r.stdout)["result"]["classes"]
        cliff = classes.get(str(man["derived"]["cliff_position"]))
        check("the cliff position is flat, which is the evidence that rules the cliff out",
              cliff is not None and abs(cliff["vs_other_classes"]) < 0.5,
              "position %d sits %+.3f pKD from the other classes over %d designs, against a "
              "cliff depth of %.2f"
              % (man["derived"]["cliff_position"], cliff["vs_other_classes"], cliff["n"],
                 man["params"]["cliff_depth"]))

        r = cli("run_diagnostic.py", "--project", demo_root, "--round", "4",
                "--test", "calibration_by_region", "--offset", "bridge")
        corrected = json.loads(r.stdout)["result"]
        check("correcting round 4 by its bridge does not account for the round",
              cal["coverage"] < 0.2 and 0.3 < corrected["coverage"] < 0.75
              and abs(corrected["mean_residual"]) > 0.5,
              "coverage %.2f raw, %.2f after a %+.3f correction, against %.2f nominal, and "
              "%+.3f pKD of discrepancy still unexplained"
              % (cal["coverage"], corrected["coverage"], corrected["offset_applied"],
                 corrected["nominal_coverage"], corrected["mean_residual"]))

    print("\nPhase 4: what the decision writer refuses")
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = os.path.join(tmp, "demo-trastuzumab")
        shutil.copytree(demo_root, sandbox)
        # The exports are gitignored and regenerable from the committed store,
        # so this pulls its own copy rather than assuming one is lying about.
        store = os.path.join(tmp, "store.json")
        shutil.copyfile(os.path.join(REPO, "lims_store", "demo-trastuzumab.json"), store)
        results4 = os.path.join(tmp, "round4.csv")
        subprocess.run([sys.executable, os.path.join(REPO, "lims.py"), "pull",
                        "--project", sandbox, "--round", "R4", "--out", results4,
                        "--store", store], cwd=REPO, capture_output=True, text=True)
        # These are tests of what a *first* proposal is refused for, so the
        # sandbox starts round 4 without one. The committed project carries
        # decision_004 -- the hour-5 gate wrote it -- and the writer would
        # otherwise refuse every payload below for already having a record,
        # which would pass the checks for the wrong reason.
        os.remove(os.path.join(sandbox, "decisions", "decision_004.json"))

        def propose(payload, round_id=4):
            path = os.path.join(tmp, "payload.json")
            with open(path, "w") as fh:
                json.dump(payload, fh)
            return cli("record_decision.py", "--project", sandbox,
                       "--round", str(round_id), "--propose", path)

        def hypothesis(**kw):
            base = {"claim": "the assay moved", "diagnostic": "offset_from_controls",
                    "reading": "supported"}
            base.update(kw)
            return base

        def payload(**kw):
            base = {
                "hypotheses": [hypothesis()],
                "recommendation": {
                    "action": "apply_offset_correction", "confidence": "high",
                    "rationale": "the bridge is clean", "alternative_considered": "the cliff",
                    "if_wrong": "the shared designs would not carry it",
                },
            }
            base.update(kw)
            return base

        r = propose(payload(hypotheses=[hypothesis(result={"offset_pkd": -0.81})]))
        check("it refuses a payload that supplies its own number",
              r.returncode != 0 and "Results come from the diagnostic" in r.stderr,
              "CLAUDE.md non-negotiable 7: the model produces no numbers")
        r = propose(payload(hypotheses=[hypothesis(diagnostic="check_the_vibes")]))
        check("it refuses a hypothesis naming a test outside the template's list",
              r.returncode != 0 and "does not permit" in r.stderr,
              "the permitted diagnostics are a template declaration, enforced in code")
        r = propose(payload(hypotheses=[hypothesis(diagnostic="residual_by_plate")]))
        check("it refuses a correction with no bridge test behind it",
              r.returncode != 0 and "offset_from_controls" in r.stderr,
              "SKILL.md rule 2: never pool across assay versions without a bridging set")
        rec = dict(payload()["recommendation"], if_wrong="")
        r = propose(payload(recommendation=rec))
        check("it refuses a recommendation that will not say what would falsify it",
              r.returncode != 0 and "if_wrong" in r.stderr,
              "the field a sceptical scientist reads first is not optional")
        rec = dict(payload()["recommendation"], confidence="refuses")
        r = propose(payload(recommendation=rec))
        check("it refuses a refusal that recommends an action anyway",
              r.returncode != 0 and "no_action" in r.stderr,
              "confidence 'refuses' pairs with no_action and nothing else")

        # The push-back round trip, which is acceptance criterion 8 in miniature.
        r = propose(payload())
        ok = r.returncode == 0
        r = cli("record_decision.py", "--project", sandbox, "--round", "4",
                "--rule", "more_evidence_requested", "--by", "check.py",
                "--request", "calibration_by_region", "--note", "show me coverage")
        ok = ok and r.returncode == 0
        rec4 = schema.read_json(os.path.join(sandbox, "decisions", "decision_004.json"))
        check("a ruling can hand the work back, naming the test it wants",
              ok and rec4["status"] == "awaiting_evidence"
              and rec4["ruling"]["requested"]["diagnostic"] == "calibration_by_region",
              "status %r, asked for %s"
              % (rec4["status"], rec4["ruling"]["requested"]["diagnostic"]))
        r = propose(payload())
        check("it refuses a second pass that ignores what the ruling asked for",
              r.returncode != 0 and "does not run it" in r.stderr,
              "answering a push-back means running what was asked for")
        r = propose(payload(hypotheses=[
            hypothesis(),
            hypothesis(claim="the offset does not restore coverage",
                       diagnostic="calibration_by_region", args={"offset": "bridge"},
                       reading="not supported")]))
        ok = r.returncode == 0
        r = cli("record_decision.py", "--project", sandbox, "--round", "4",
                "--rule", "accepted_with_modification", "--by", "check.py",
                "--note", "correct the offset, and widen exploration next round")
        rec4 = schema.read_json(os.path.join(sandbox, "decisions", "decision_004.json"))
        check("the second pass, its extra test and the final ruling are all kept",
              ok and r.returncode == 0 and rec4["n_passes"] == 2
              and rec4["status"] == "ruled"
              and rec4["passes"][0]["ruling"]["verdict"] == "more_evidence_requested"
              and rec4["passes"][1]["answering"] == "calibration_by_region",
              "%d passes, %s then %s" % (rec4["n_passes"],
                                         rec4["passes"][0]["ruling"]["verdict"],
                                         rec4["passes"][1]["ruling"]["verdict"]))

        # Every number in the record has to come back the same when re-run.
        sb = project.load(sandbox)
        drifted = []
        for h in rec4["hypotheses"]:
            again = diagnostics.run(
                h["diagnostic"], project.read_artifact(sb, "evidence", 4),
                project.read_artifact(sb, "batches", 4), project.designs_by_id(sb),
                policy=sb["objectives"]["diagnostics_policy"], args=dict(h["args"]))
            if schema.content_hash(again) != schema.content_hash(h["result"]):
                drifted.append(h["diagnostic"])
        check("every number in the record reproduces when its test is re-run",
              not drifted, "%d results recomputed from the hashed inputs"
              % len(rec4["hypotheses"]))

        r = cli("import_round.py", "--project", sandbox, "--round", "4", "--results",
                results4,
                "--offset", "always", "--authority", "decision_004")
        check("a ruling that authorizes the correction lets the frame move",
              r.returncode == 0 and schema.read_json(
                  os.path.join(sandbox, "evidence", "snapshot_004.json")
              )["frame"]["authority"] == "decision_004",
              "and CLAUDE.md non-negotiable 6: the action runs in code, after the ruling")
        r = cli("import_round.py", "--project", sandbox, "--round", "4", "--results",
                results4,
                "--offset", "always", "--authority", "decision_002")
        check("a correction cannot cite a ruling that recommended something else",
              r.returncode != 0 and "refit_only" in r.stderr,
              "decision_002 ruled refit_only, so it authorizes no change to the data")

    # The fourth verb, in its own sandbox because a record is closed once ruled.
    with tempfile.TemporaryDirectory() as tmp:
        sandbox = os.path.join(tmp, "demo-trastuzumab")
        shutil.copytree(demo_root, sandbox)
        store = os.path.join(tmp, "store.json")
        shutil.copyfile(os.path.join(REPO, "lims_store", "demo-trastuzumab.json"), store)
        results4 = os.path.join(tmp, "round4.csv")
        subprocess.run([sys.executable, os.path.join(REPO, "lims.py"), "pull",
                        "--project", sandbox, "--round", "R4", "--out", results4,
                        "--store", store], cwd=REPO, capture_output=True, text=True)
        # These are tests of what a *first* proposal is refused for, so the
        # sandbox starts round 4 without one. The committed project carries
        # decision_004 -- the hour-5 gate wrote it -- and the writer would
        # otherwise refuse every payload below for already having a record,
        # which would pass the checks for the wrong reason.
        os.remove(os.path.join(sandbox, "decisions", "decision_004.json"))
        path = os.path.join(tmp, "payload.json")
        with open(path, "w") as fh:
            json.dump({"hypotheses": [{"claim": "plate R4P2 ran low",
                                       "diagnostic": "residual_by_plate",
                                       "reading": "supported"}],
                       "recommendation": {"action": "drop_wells", "confidence": "medium",
                                          "parameters": {"plates": ["R4P2"]},
                                          "rationale": "the plate, not the molecules",
                                          "alternative_considered": "an offset correction",
                                          "if_wrong": "the remaining plate would read low too"}},
                      fh)
        ok = cli("record_decision.py", "--project", sandbox, "--round", "4",
                 "--propose", path).returncode == 0
        ok = ok and cli("record_decision.py", "--project", sandbox, "--round", "4",
                        "--rule", "accepted", "--by", "check.py",
                        "--note", "drop it").returncode == 0
        r = cli("import_round.py", "--project", sandbox, "--round", "4",
                "--results", results4, "--drop-plate", "R4P2",
                "--authority", "decision_004")
        snap = schema.read_json(os.path.join(sandbox, "evidence", "snapshot_004.json"))
        dropped = snap["reconciliation"]["dropped"]
        check("the fourth verb runs too: a ruling can drop a plate's wells",
              ok and r.returncode == 0 and dropped["rows"] == 48
              and dropped["authority"] == "decision_004"
              and sorted({p for m in snap["measurements"] for p in m["plates"]}) == ["R4P1"],
              "%d wells on %s discarded before the join, %d designs left"
              % (dropped["rows"], ", ".join(dropped["plates"]),
                 snap["reconciliation"]["designs"]))
        r = cli("import_round.py", "--project", sandbox, "--round", "4",
                "--results", results4, "--drop-plate", "R4P2")
        check("and it cannot be done without one",
              r.returncode != 0 and "no action is taken on an unruled record" in r.stderr,
              "discarding wells is an action, and actions need a ruling")

    print("\nPhase 4: round 2 in the committed demo project")
    dec2 = project.read_decision(demo, 2)
    snap2 = project.read_artifact(demo, "evidence", 2)
    check("round 2 flags in the opposite direction to round 4",
          snap2["flagged"] and snap2["anomaly"]["mean_signed_residual"] > 0.5
          and snap4["anomaly"]["mean_signed_residual"] < -0.5,
          "round 2 %+.3f, round 4 %+.3f pKD -- the same statistic, two correct answers"
          % (snap2["anomaly"]["mean_signed_residual"],
             snap4["anomaly"]["mean_signed_residual"]))
    check("round 2 is ruled, and the ruling changed no measurement",
          dec2 is not None and dec2["status"] == "ruled"
          and dec2["recommendation"]["action"] == "refit_only"
          and snap2["frame"]["offset_applied"] == 0.0
          and all(m["value"] == m["raw_value"] for m in snap2["measurements"]
                  if m["value"] is not None),
          "%s, %s by %s" % (dec2["recommendation"]["action"], dec2["ruling"]["verdict"],
                            dec2["ruling"]["by"]))
    check("ruled-ness is read from the decision record, not from the frame",
          project.is_ruled(demo, 2) and snap2["frame"]["authority"] == "unruled",
          "a ruling that changes no data moves no frame, and round 2 is still ruled")
    check("the ruling unblocked the loop and round 4 is where it stops now",
          project.unruled_flagged_rounds(demo) == [4]
          and project.read_artifact(demo, "models", 2) is not None,
          "rounds still waiting on a human: %s" % project.unruled_flagged_rounds(demo))
    check("its hypotheses cover every explanation, including the ones rejected",
          len({h["diagnostic"] for h in dec2["hypotheses"]}) == 5
          and sum(1 for h in dec2["hypotheses"] if h["reading"] == "not supported") >= 3,
          "%d hypotheses over all five tests, %d of them unsupported"
          % (len(dec2["hypotheses"]),
             sum(1 for h in dec2["hypotheses"] if h["reading"] == "not supported")))
    check("its ad hoc analysis is labelled one-off and carries its own source",
          all(a["code"] and "one-off, unversioned" in a["note"] for a in dec2["ad_hoc"]),
          "%d ad hoc results, none of them an input to a code path" % len(dec2["ad_hoc"]))
    check("every hypothesis in it points at the snapshot and batch it was computed from",
          all(h["inputs"]["snapshot"] == snap2["hash"] for h in dec2["hypotheses"]),
          "snapshot %s" % schema.short_hash(snap2["hash"]))


    print("\nPhase 5 gate: round 4's decision record (SPEC.md acceptance criterion 3)")
    # Written by a Claude Code session given only the skill and the connectors,
    # in a tree with no README, SPEC, DECISIONS or CLAUDE.md in it. What is
    # checked here is the record, not the transcript: the claim is that the
    # skill and the five tests are sufficient, and a record that holds up is
    # what sufficient looks like.
    demo = project.load(demo_root)
    dec4 = project.read_decision(demo, 4)
    snap4 = project.read_artifact(demo, "evidence", 4)
    batch4 = project.read_artifact(demo, "batches", 4)
    by_test = {}
    for h in dec4["hypotheses"]:
        by_test.setdefault(h["diagnostic"], []).append(h["reading"])

    check("round 4 carries a decision record and it verifies",
          schema.verify(dec4) and dec4["round"] == 4,
          "%s, %d hypotheses over %d of the five tests"
          % (dec4["id"], len(dec4["hypotheses"]), len(by_test)))
    check("it identifies the offset rather than the whole discrepancy",
          any(r in ("supported", "partially supported")
              for r in by_test.get("offset_from_controls", []))
          and dec4["recommendation"]["action"] == "apply_offset_correction",
          "bridge -1.014 against a -2.046 round: correct what the bridge supports")
    check("it rejects the plate and the unstable read with the tests that reject them",
          by_test.get("residual_by_plate") == ["not supported"]
          and by_test.get("replicate_concordance") == ["not supported"],
          "both plates displaced equally, and no replicate outside tolerance")
    check("it ran the counterfactual and says what the correction leaves behind",
          any(h["args"].get("offset") == "bridge"
              for h in dec4["hypotheses"] if h["diagnostic"] == "calibration_by_region"),
          "calibration_by_region --offset bridge is what makes the remainder visible")
    check("it says what would falsify it, and it is not left open",
          len(dec4["recommendation"]["if_wrong"].split()) > 20
          and dec4["recommendation"]["alternative_considered"],
          "%d words of if_wrong" % len(dec4["recommendation"]["if_wrong"].split()))
    check("the sixth question is in ad_hoc, with its source and its label",
          dec4["ad_hoc"] and all(a["code"] and "one-off, unversioned" in a["note"]
                                 for a in dec4["ad_hoc"]),
          "%d ad hoc cuts, none of them an input to a code path" % len(dec4["ad_hoc"]))
    check("every number in it reproduces when its test is re-run",
          not [h["diagnostic"] for h in dec4["hypotheses"]
               if schema.content_hash(diagnostics.run(
                   h["diagnostic"], snap4, batch4, project.designs_by_id(demo),
                   policy=demo["objectives"]["diagnostics_policy"],
                   args=dict(h["args"]))) != schema.content_hash(h["result"])],
          "%d results recomputed from the hashed inputs" % len(dec4["hypotheses"]))
    check("it points at the snapshot and batch it was computed from",
          dec4["inputs"]["snapshot"] == snap4["hash"]
          and dec4["inputs"]["batch"] == batch4["hash"],
          "snapshot %s" % schema.short_hash(snap4["hash"]))
    check("and it is unruled, because the agent proposes and does not dispose",
          dec4["status"] == "open" and dec4["ruling"] is None
          and not project.is_ruled(demo, 4)
          and project.unruled_flagged_rounds(demo) == [4],
          "round 4 is still waiting on a named human, which is the product working")

    print("\nPhase 5: the registry connector (SPEC.md acceptance criterion 6)")
    import lims as lims_mod
    from core import scoring

    # Decision 90: the directory is connectors/ and not mcp/, because a bare
    # directory named mcp/ is a namespace package and shadows the SDK the
    # servers import whenever the repo root is on sys.path. That was tested
    # rather than assumed, and this is the test.
    import mcp as mcp_sdk
    sdk_path = os.path.abspath(list(mcp_sdk.__path__)[0])
    check("the connector directory does not shadow the MCP SDK",
          not os.path.isdir(os.path.join(REPO, "mcp"))
          and os.path.basename(os.path.dirname(sdk_path)) == "site-packages",
          "with the repo root on sys.path, import mcp still reaches site-packages")

    conn_src = {name: open(os.path.join(REPO, "connectors", name)).read()
                for name in ("registry_server.py", "bioprovider_server.py")}
    # stdout *is* the JSON-RPC stream. A stray print breaks the connector for
    # every client, and nothing else in the build would notice.
    stray = []
    for name, src in conn_src.items():
        for fn in [n for n in ast.parse(src, filename=name).body
                   if isinstance(n, ast.FunctionDef) and n.name != "main"]:
            if any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                   and n.func.id == "print" for n in ast.walk(fn)):
                stray.append("%s:%s" % (name, fn.name))
    check("no connector prints outside its --tools branch", not stray,
          "stdout is the JSON-RPC stream; a stray print breaks every client")
    check("the bioprovider never reaches the simulated lab",
          "import data" not in conn_src["bioprovider_server.py"]
          and "from data" not in conn_src["bioprovider_server.py"],
          "the oracle is the registry's, behind lims.py, and nothing else imports it")

    P = os.path.join("projects", "demo-trastuzumab")
    reg = mcp_session("registry_server.py")
    pull, resubmit, missing, listing = reg([
        ("pull_assay_results", {"project": P, "round_id": "R4"}),
        ("submit_batch", {"project": P, "round": 4}),
        ("get_construct", {"project": P, "construct_id": "CST99999"}),
        ("list_designs", {"project": P, "limit": 3})])["results"]
    served = set(mcp_session("registry_server.py")([])["tools"])
    withheld = {"create_sample", "edit_assay_result", "start_workflow", "delete_record"}

    check("the registry connector serves exactly the declared tool list",
          served == {name for name, _ in lims_mod.TOOLS}, ", ".join(sorted(served)))
    check("and none of the four withheld tools exists on it",
          not (served & withheld),
          "no " + ", ".join(sorted(withheld)))
    tool_help = subprocess.run(
        [sys.executable, os.path.join(REPO, "connectors", "registry_server.py"), "--tools"],
        cwd=REPO, capture_output=True, text=True).stdout
    check("and the tool list says so out loud, which is the boundary claim",
          all(w in tool_help for w in withheld) and "deliberately" in tool_help,
          "the answer to 'does this replace the LIMS' is a tool list")

    # Non-negotiable 2 at the connector layer: same bytes, different transport.
    direct = lims_mod.rows_to_csv(
        lims_mod.Registry(lims_mod.store_path_for(P)).pull_assay_results("R4"))
    written = open(os.path.join(REPO, pull["data"]["path"])).read()
    check("the connector and the CLI export byte-identical rows",
          written == direct and pull["data"]["n_rows"] == 96,
          "%d rows, %d bytes, assay version %s"
          % (pull["data"]["n_rows"], len(written), pull["data"]["assay_version"]))
    check("a round cannot be submitted twice, and the refusal says why",
          resubmit["error"] and "already been submitted" in resubmit["text"],
          "the registry does not overwrite assay data")
    check("a refusal reaches the caller as a message, not as a crash",
          missing["error"] and "CST99999" in missing["text"],
          "ToolError carries the reason; a bare exception reaches the agent as noise")
    check("list_designs caps what it returns and says what it held back",
          listing["data"]["n_shown"] == 3 and listing["data"]["n_total"] > 3,
          "%d of %d" % (listing["data"]["n_shown"], listing["data"]["n_total"]))

    print("\nPhase 5: the provider interface, and what it refuses to fake")
    state = project.load(os.path.join(REPO, P))
    by_id = project.designs_by_id(state)
    ids = list(by_id)[:4]
    bio = mcp_session("bioprovider_server.py")
    embed, esm, scored, struct = bio([
        ("embed_sequences", {"project": P, "model": "onehot", "sequences": ids}),
        ("embed_sequences", {"project": P, "model": "esm2_t12_35M_UR50D", "sequences": ids}),
        ("score_properties", {"project": P, "tool_set": "developability", "candidates": ids}),
        ("predict_structures", {"project": P, "model": "boltz", "complexes": ids})])["results"]

    check("the bioprovider serves exactly the three declared tools",
          set(bio([])["tools"]) == {"embed_sequences", "score_properties",
                                    "predict_structures"},
          "embed_sequences, score_properties, predict_structures")

    parent, region = state["designs"]["parent"], state["objectives"]["editable_region"]
    X = encode.one_hot([by_id[i]["sequence"] for i in ids], region)
    own = schema.content_hash({"onehot": [[float(v) for v in row] for row in X]})
    check("embed_sequences returns the block core/ computes, hash for hash",
          embed["data"]["hash"] == own and embed["data"]["shape"] == [len(ids), 160],
          "%s, %d x 160, %d ones per row"
          % (schema.short_hash(own), len(ids), embed["data"]["ones_per_row"]))
    check("an unwired backend is refused, and the refusal names what is missing",
          esm["error"] and "esm_live" in esm["text"] and "not wired" in esm["text"],
          "no silent fallback to one-hot -- failure mode 1 in the one swappable layer")

    agree = all(
        abs(row["hydrophobicity"]
            - scoring.hydrophobicity(by_id[row["design_id"]]["sequence"], region)) < 1e-12
        and row["liability_count"] == scoring.liability_count(
            by_id[row["design_id"]]["sequence"], parent, region)
        for row in scored["data"]["results"])
    check("score_properties agrees with the filter enforcing the same numbers",
          agree and scored["data"]["source"] == "computed",
          "%d designs, %d passing, computed rather than predicted"
          % (scored["data"]["n"], scored["data"]["n_passing"]))
    check("predict_structures returns no number and says it is stubbed",
          struct["data"]["status"] == "stubbed" and struct["data"]["computed"] is False
          and all(x["prediction"] is None and x["confidence"] is None
                  for x in struct["data"]["results"]),
          "a stub that invented a pLDDT would be the exact failure this build is about")

    print("\nPhase 5: the plugin is installable, not merely described")
    plugin = schema.read_json(os.path.join(REPO, ".claude-plugin", "plugin.json"))
    market = schema.read_json(os.path.join(REPO, ".claude-plugin", "marketplace.json"))
    root_mcp = schema.read_json(os.path.join(REPO, ".mcp.json"))
    check("the marketplace declares one plugin and it is this directory",
          len(market["plugins"]) == 1 and market["plugins"][0]["source"] == "./"
          and market["plugins"][0]["name"] == plugin["name"],
          "%s -> %s" % (market["name"], plugin["name"]))
    check("the plugin bundles the skill where a loader looks for it",
          os.path.isfile(os.path.join(REPO, "skills", "adaptive-optimization", "SKILL.md")),
          "skills/adaptive-optimization/SKILL.md")
    check("both connectors are registered in both launch contexts",
          set(plugin["mcpServers"]) == set(root_mcp["mcpServers"])
          == {"registry", "bioprovider"},
          "plugin root for an install, repo-relative for a clone")
    named = [a for spec in list(plugin["mcpServers"].values()) + list(root_mcp["mcpServers"].values())
             for a in [spec["command"]] + spec["args"]]
    check("every path either manifest names exists",
          all(os.path.isfile(os.path.join(
              REPO, p.replace("${CLAUDE_PLUGIN_ROOT}/", "").replace("./", "")))
              for p in named),
          "%d paths, the interpreter and both connectors" % len(named))

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
