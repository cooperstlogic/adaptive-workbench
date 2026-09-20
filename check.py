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


def cli_replay_of(files):
    """Run the browser's own sequence through the CLI and compare the bytes.

    The browser claims to be the same science on a different runtime. This
    drives the CLI scripts over the same starting state, in the same order,
    with the same arguments and no approver named, and returns which files
    came out identical. Two cannot: a decision record carries the moment a
    person ruled, and rounds.json carries the moments the graph was rewritten.
    """
    from core import schema  # noqa: PLC0415

    web_out = os.path.join(REPO, "web", "public", "workbench")
    scripts = os.path.join(REPO, "skills", "adaptive-optimization", "scripts")
    prefix = "projects/demo-trastuzumab/"
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "demo-trastuzumab")
        shutil.copytree(os.path.join(web_out, "projects", "demo-trastuzumab"), root)
        store = os.path.join(tmp, "store.json")
        shutil.copyfile(os.path.join(web_out, "lims_store", "demo-trastuzumab.json"), store)
        exports = os.path.join(tmp, "exports")
        os.makedirs(exports)
        csv_path = os.path.join(exports, "demo-trastuzumab_round4.csv")
        payload = schema.read_json(os.path.join(web_out, "reference",
                                                "decision_004.proposal.json"))
        proposals = []
        for p in payload["passes"]:
            path = os.path.join(tmp, "proposal_004_pass%d.json" % p["pass"])
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"trigger": payload["trigger"], "hypotheses": p["hypotheses"],
                           "recommendation": p["recommendation"],
                           "ad_hoc": [dict(a, stdout="") for a in p["ad_hoc"]]},
                          fh, indent=1)
            proposals.append((path, p.get("ruling")))

        def run(*argv):
            r = subprocess.run([sys.executable] + list(argv), cwd=REPO,
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("%s\n%s" % (argv[0], r.stderr or r.stdout))

        lims = os.path.join(REPO, "lims.py")
        S = lambda name: os.path.join(scripts, name)  # noqa: E731
        run(S("select_batch.py"), "--project", root, "--round", "4")
        run(lims, "submit", "--project", root, "--round", "4", "--store", store)
        run(lims, "pull", "--project", root, "--round", "R4", "--out", csv_path,
            "--store", store)
        run(S("import_round.py"), "--project", root, "--round", "4", "--results", csv_path,
            "--offset", "if-clear", "--authority", "bridge_policy:browser --offset if-clear")
        run(S("evaluate_prior.py"), "--project", root, "--round", "4")
        # The browser's sequence: each recorded pass proposed, the recorded
        # push-back ruled between them, the last pass accepted.
        for path, ruling in proposals:
            run(S("record_decision.py"), "--project", root, "--round", "4", "--propose", path)
            if ruling and ruling["verdict"] == "more_evidence_requested":
                run(S("record_decision.py"), "--project", root, "--round", "4",
                    "--rule", "more_evidence_requested", "--by", "check.py",
                    "--note", ruling["note"], "--request", ruling["requested"]["diagnostic"])
        run(S("record_decision.py"), "--project", root, "--round", "4", "--rule", "accepted",
            "--by", "check.py", "--note", "ruled by web/scripts/pyodide-check.mjs")
        run(S("import_round.py"), "--project", root, "--round", "4", "--results", csv_path,
            "--offset", "always", "--authority", "decision_004")
        run(S("evaluate_prior.py"), "--project", root, "--round", "4")
        run(S("fit_surrogates.py"), "--project", root, "--round", "4")
        run(S("generate_candidates.py"), "--project", root, "--round", "5")
        run(S("select_batch.py"), "--project", root, "--round", "5")

        same, drifted = [], []
        for rel, text in sorted(files.items()):
            if not rel.startswith(prefix):
                continue
            path = os.path.join(root, rel[len(prefix):])
            got = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
            (same if got == text else drifted).append(rel[len(prefix):])
        return same, drifted


def cli_instantiation_of(files, name="harness-instantiated",
                         created="2026-01-01T00:00:00+00:00"):
    """Instantiate the same project through the CLI and compare the bytes.

    Decision 108 -- "no project instantiation from a declaration" -- graded
    *survives, but under-tested* in the phase-5b audit. This is the form of it
    a machine can check: the browser ran `init_project.py` and round 1's two
    scripts through Pyodide, the CLI runs the identical three commands here,
    and a template that instantiates the same project on two runtimes is a
    declaration rather than a prompt. The timestamp is pinned with --created,
    because that is the only thing in the four files that is not a pure
    function of the template and the three facts a person supplies.
    """
    scripts = os.path.join(REPO, "skills", "adaptive-optimization", "scripts")
    prefix = "projects/%s/" % name
    mine = {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)}
    if not mine:
        return [], ["the browser instantiated no project"]
    with tempfile.TemporaryDirectory() as tmp:
        def run(*argv):
            r = subprocess.run([sys.executable] + list(argv), cwd=REPO,
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("%s\n%s" % (argv[0], r.stderr or r.stdout))

        run(os.path.join(REPO, "init_project.py"),
            "--template", "antibody-affinity-maturation", "--name", name,
            "--lead", "trastuzumab", "--target", "HER2", "--team", "check.py",
            "--created", created, "--projects-dir", tmp)
        root = os.path.join(tmp, name)
        run(os.path.join(scripts, "generate_candidates.py"), "--project", root, "--round", "1")
        run(os.path.join(scripts, "select_batch.py"), "--project", root, "--round", "1")

        same, drifted = [], []
        for rel, text in sorted(mine.items()):
            path = os.path.join(root, rel)
            got = open(path, encoding="utf-8").read() if os.path.isfile(path) else None
            (same if got == text else drifted).append(rel)
        return same, drifted


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
    # Since phase 7 the record is two-pass: the gate's diagnosis is pass 1,
    # a named person sent it back, and a second gate run answered. These
    # checks read pass 1, which is what the hour-5 gate wrote; the push-back
    # and its answer are checked under phase 7.
    demo = project.load(demo_root)
    dec4 = project.read_decision(demo, 4)
    snap4 = project.read_artifact(demo, "evidence", 4)
    batch4 = project.read_artifact(demo, "batches", 4)
    pass1 = dec4["passes"][0]
    by_test = {}
    for h in pass1["hypotheses"]:
        by_test.setdefault(h["diagnostic"], []).append(h["reading"])

    check("round 4 carries a decision record and it verifies",
          schema.verify(dec4) and dec4["round"] == 4,
          "%s, %d hypotheses over %d of the five tests in pass 1"
          % (dec4["id"], len(pass1["hypotheses"]), len(by_test)))
    check("it identifies the offset rather than the whole discrepancy",
          any(r in ("supported", "partially supported")
              for r in by_test.get("offset_from_controls", []))
          and pass1["recommendation"]["action"] == "apply_offset_correction",
          "bridge -1.014 against a -2.046 round: correct what the bridge supports")
    check("it rejects the plate and the unstable read with the tests that reject them",
          by_test.get("residual_by_plate") == ["not supported"]
          and by_test.get("replicate_concordance") == ["not supported"],
          "both plates displaced equally, and no replicate outside tolerance")
    check("it ran the counterfactual and says what the correction leaves behind",
          any(h["args"].get("offset") == "bridge"
              for h in pass1["hypotheses"] if h["diagnostic"] == "calibration_by_region"),
          "calibration_by_region --offset bridge is what makes the remainder visible")
    check("it says what would falsify it, and it is not left open",
          len(pass1["recommendation"]["if_wrong"].split()) > 20
          and pass1["recommendation"]["alternative_considered"],
          "%d words of if_wrong" % len(pass1["recommendation"]["if_wrong"].split()))
    check("the sixth question is in ad_hoc, with its source and its label",
          pass1["ad_hoc"] and all(a["code"] and "one-off, unversioned" in a["note"]
                                  for a in pass1["ad_hoc"]),
          "%d ad hoc cuts, none of them an input to a code path" % len(pass1["ad_hoc"]))
    every = [h for p in dec4["passes"] for h in p["hypotheses"]]
    check("every number in it reproduces when its test is re-run",
          not [h["diagnostic"] for h in every
               if schema.content_hash(diagnostics.run(
                   h["diagnostic"], snap4, batch4, project.designs_by_id(demo),
                   policy=demo["objectives"]["diagnostics_policy"],
                   args=dict(h["args"]))) != schema.content_hash(h["result"])],
          "%d results over %d passes recomputed from the hashed inputs"
          % (len(every), len(dec4["passes"])))
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
    # Phase 5b pinned this shape after reading the wire in Claude Science, whose
    # bundled SDK is mcp 1.x. Both SDK versions prefix the text with "Error
    # executing tool <name>: " -- that prefix is theirs and is not removable.
    # What ToolError buys is the sentence after it, so the sentence is what is
    # asserted, and the prefix is asserted too so nobody re-words the README
    # into claiming it is absent -- decision 104.
    check("the refusal is isError with the reason after the SDK's own prefix",
          resubmit["error"] is True
          and resubmit["text"].startswith("Error executing tool submit_batch: ")
          and "has already been submitted" in resubmit["text"].split(": ", 1)[1],
          "the prefix is the SDK's on 1.x and 2.x alike; the sentence after it is ours")
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

    print("\nPhase 6: the browser bundle is the repository, not a copy of it")
    sys.path.insert(0, os.path.join(REPO, "web"))
    import bundle as web_bundle  # noqa: PLC0415

    OUT = web_bundle.OUT
    fresh, why = web_bundle.check()
    check("the bundle the site serves is the one this repository would write now",
          fresh, why or "web/bundle.py --check")
    manifest = (schema.read_json(os.path.join(OUT, "manifest.json"))
                if os.path.isfile(os.path.join(OUT, "manifest.json")) else {"code": []})
    verbatim = [e for e in manifest["code"] if e.get("verbatim")]
    identical = [e for e in verbatim
                 if os.path.isfile(os.path.join(REPO, e["path"]))
                 and open(os.path.join(REPO, e["path"]), "rb").read()
                 == open(os.path.join(OUT, e["path"]), "rb").read()]
    check("every module the browser executes is the repository's, byte for byte",
          len(identical) == len(verbatim) and len(verbatim) >= 20,
          "%d of %d files; CLAUDE.md non-negotiable 2 applied to the surface most "
          "tempted to fork" % (len(identical), len(verbatim)))
    check("and they are laid out in the repo's own shape, so every import resolves",
          all(os.path.isfile(os.path.join(OUT, rel)) for rel in
              ("core/diagnostics.py", "data/oracle.py", "lims.py",
               "skills/adaptive-optimization/scripts/import_round.py")),
          "core/, data/, lims.py and the scripts, where dirname(__file__) expects them")
    check("nothing under web/src/ is Python, and no driver logic hides in the page",
          not [f for _d, _s, fs in os.walk(os.path.join(REPO, "web", "src"))
               for f in fs if f.endswith(".py")],
          "the page calls wb_driver; wb_driver calls the scripts; the scripts call core/")

    print("\nPhase 6: the state the browser opens on is derived, not hand-written")
    demo = os.path.join(REPO, "projects", "demo-trastuzumab")
    web_project = os.path.join(OUT, "projects", "demo-trastuzumab")
    committed_batch = schema.read_json(os.path.join(demo, "batches", "batch_004.json"))
    shipped_batch = schema.read_json(os.path.join(web_project, "batches", "batch_004.json"))
    differ = sorted(k for k in set(shipped_batch) | set(committed_batch)
                    if shipped_batch.get(k) != committed_batch.get(k))
    check("the shipped round-4 batch is the committed one with the signature taken off",
          differ == ["approval", "hash"]
          and shipped_batch["approval"]["status"] == "unreviewed",
          "differs in %s and nothing else" % ", ".join(differ))
    def has_time(obj):
        """Any ISO timestamp anywhere in the record, at any depth."""
        if isinstance(obj, dict):
            return any(has_time(v) for v in obj.values())
        if isinstance(obj, list):
            return any(has_time(v) for v in obj)
        return isinstance(obj, str) and len(obj) >= 19 and obj[4] == "-" and obj[10] == "T"

    check("and it therefore carries no timestamp, which is what makes its hash portable",
          not has_time(shipped_batch) and has_time(committed_batch),
          "%s is a pure function of the pool, the model run and the objectives; the "
          "committed one carries the moment it was signed and can never be reproduced"
          % schema.short_hash(shipped_batch["hash"]))
    check("the round the visitor is asked to approve has not been run yet",
          not os.path.exists(os.path.join(web_project, "evidence", "snapshot_004.json"))
          and not os.path.exists(os.path.join(web_project, "decisions",
                                              "decision_004.json"))
          and os.path.isfile(os.path.join(web_project, "candidates", "pool_004.json")),
          "pool and batch present; snapshot, evaluation and decision absent")
    store = schema.read_json(os.path.join(OUT, "lims_store", "demo-trastuzumab.json"))
    check("and the registry has not been sent it either",
          set(store["rounds"]) == {"R1", "R2", "R3"}
          and store["next_construct"] == len(store["constructs"]) + 1,
          "%d constructs, next %s -- the round-4 designs get their ids when submitted"
          % (len(store["constructs"]), store["next_construct"]))

    proposal = schema.read_json(os.path.join(OUT, "reference", "decision_004.proposal.json"))
    shipped_h = [h for p in proposal["passes"] for h in p["hypotheses"]]
    carried = ([k for h in shipped_h for k in ("result", "source", "inputs") if k in h]
               + [k for p in proposal["passes"] for a in p["ad_hoc"] for k in ("stdout",)
                  if k in a])
    check("the shipped proposal carries claims and no numbers",
          not carried and len(shipped_h) >= 8
          and all(h.get("diagnostic") and h.get("reading") for h in shipped_h),
          "%d hypotheses over %d passes, every result and every ad hoc stdout stripped; "
          "record_decision.py re-runs each test in the browser -- CLAUDE.md "
          "non-negotiable 7" % (len(shipped_h), len(proposal["passes"])))
    committed_record = schema.read_json(os.path.join(demo, "decisions",
                                                     "decision_004.json"))
    check("and it is the committed record's own claims, not a retelling of them",
          [h["claim"] for h in shipped_h]
          == [h["claim"] for p in committed_record["passes"] for h in p["hypotheses"]]
          and proposal["source_record"] == committed_record["hash"]
          and proposal["n_passes"] == committed_record["n_passes"],
          "derived from %s by web/bundle.py, pass by pass"
          % schema.short_hash(committed_record["hash"]))

    print("\nRedesign: the lab round trip -- an order goes out, and a run is waited on")
    with tempfile.TemporaryDirectory() as tmp:
        import lims as lims_mod                                   # noqa: PLC0415

        lab_root = os.path.join(tmp, "demo-trastuzumab")
        shutil.copytree(os.path.join(REPO, "web", "public", "workbench", "projects",
                                     "demo-trastuzumab"), lab_root)
        plain = os.path.join(tmp, "plain.json")
        held = os.path.join(tmp, "held.json")
        for dst in (plain, held):
            shutil.copyfile(os.path.join(REPO, "web", "public", "workbench", "lims_store",
                                         "demo-trastuzumab.json"), dst)
        open_root = os.path.join(tmp, "open-copy")
        shutil.copytree(lab_root, open_root)

        lims_mod.submit_project_batch(open_root, 4, plain)
        lims_mod.submit_project_batch(lab_root, 4, held, stagger=True)
        a = schema.read_json(plain)["rounds"]["R4"]
        b = schema.read_json(held)["rounds"]["R4"]
        volatile = ("submitted", "status", "release_on_check", "checks", "expected")
        check("staggering a round changes the record only where it says it does",
              a["status"] == "complete" and b["status"] == "running"
              and set(b) - set(a) == {"release_on_check", "checks", "expected"}
              and all(a[k] == b[k] for k in a if k not in volatile),
              "off is byte for byte what this registry has always written, so every "
              "store on disk and check.py's own six-round campaign are untouched")

        refusal = None
        try:
            lims_mod.pull_to_csv("R4", lab_root, held)
        except lims_mod.RunningError as exc:
            refusal = str(exc)
        check("the registry refuses a pull on a round still running, and says what it "
              "refused",
              refusal is not None and "R4" in refusal and "check_run_status" in refusal
              and "0 of 96" in refusal,
              (refusal or "the pull was allowed")[:96])

        first = lims_mod.run_status("R4", lab_root, held)
        second = lims_mod.run_status("R4", lab_root, held)
        check("and asking is what releases it: not ready, then ready",
              first["status"] == "running" and first["n_rows"] == 0
              and second["status"] == "complete" and second["released_now"]
              and second["n_rows"] == 96,
              "expected %s on the first ask, %d rows on the second"
              % ((first["expected"] or "?")[:10], second["n_rows"]))

        # The other way to the same place: the demo's clock, which a person
        # presses when eight days is not a thing a demo can wait for.
        bench = os.path.join(tmp, "bench.json")
        shutil.copyfile(os.path.join(REPO, "web", "public", "workbench", "lims_store",
                                     "demo-trastuzumab.json"), bench)
        bench_root = os.path.join(tmp, "bench-copy")
        shutil.copytree(lab_root, bench_root)
        lims_mod.submit_project_batch(bench_root, 4, bench, stagger=True)
        before_release = schema.read_json(bench)["rounds"]["R4"]
        released = lims_mod.release_run("R4", bench_root, bench, reason="check.py")
        after_release = schema.read_json(bench)["rounds"]["R4"]
        check("the clock can be moved by hand instead, and it moves nothing but the clock",
              released["released_now"] and before_release["status"] == "running"
              and after_release["status"] == "complete"
              and set(after_release) - set(before_release) == {"released_by", "released_at"}
              and all(after_release[k] == before_release[k]
                      for k in before_release if k != "status")
              and lims_mod.pull_to_csv("R4", bench_root, bench)["n_rows"]
              == before_release["n_rows"],
              "released by %r: the same %d rows, measured at submission, handed over on "
              "the day someone asked rather than the day the registry named"
              % (after_release["released_by"], after_release["n_rows"]))
        check("and it is a demo device rather than a registry tool, so it is not on the "
              "list that answers 'does this replace the LIMS'",
              "release_run" not in [name for name, _ in lims_mod.TOOLS]
              and lims_mod.release_run("R4", bench_root, bench)["released_now"] is False,
              "%d tools, none of which finishes an assay; releasing an already-released "
              "round is a no-op that says so" % len(lims_mod.TOOLS))

        order = lims_mod.export_order("R4", lab_root, held)
        submitted = schema.read_json(held)["rounds"]["R4"]["samples"]
        measured = {"value", "unit", "status", "well", "replicate"}
        check("the export is an order and not a result: no measured value anywhere in it",
              not (measured & set(lims_mod.ORDER_COLUMNS))
              and not any(measured & set(row) for row in order["rows"])
              and "value" not in order["csv"].splitlines()[0],
              "columns are %s" % ", ".join(lims_mod.ORDER_COLUMNS))
        check("and its rows are the submission's samples exactly, in order",
              [r["sample_id"] for r in order["rows"]] == [s["sample_id"] for s in submitted]
              and [r["design_id"] for r in order["rows"]]
              == [s["design_id"] for s in submitted]
              and order["n_rows"] == len(submitted),
              "%d rows, %d samples -- an order the lab could act on, and nothing else"
              % (order["n_rows"], len(submitted)))
        pulled = lims_mod.pull_to_csv("R4", lab_root, held)
        check("a released round pulls the rows it always did",
              pulled["n_rows"] == 96 and pulled["assay_version"] == "v1.3",
              "%d rows, assay %s -- the values were measured at submission either way"
              % (pulled["n_rows"], pulled["assay_version"]))

    registry = mcp_session("registry_server.py")
    out = registry([("check_run_status", {"project": "projects/demo-trastuzumab",
                                          "round_id": "R3"}),
                    ("export_submission", {"project": "projects/demo-trastuzumab",
                                           "round_id": "R3",
                                           "out": os.path.join(tempfile.gettempdir(),
                                                               "check_order_R3.csv")})])
    check("both new tools are on the registry connector, over the transport a host uses",
          {"check_run_status", "export_submission"} <= set(out["tools"])
          and not any(r["error"] for r in out["results"])
          and out["results"][0]["data"]["status"] == "complete"
          and out["results"][1]["data"]["n_rows"] == 48,
          "%d tools now; both are reads a LIMS unambiguously owns, and the write path "
          "did not move" % len(out["tools"]))
    check("and the withheld list is still the answer to 'does this replace the LIMS'",
          not ({"create_sample", "edit_assay_result", "start_workflow", "delete_record"}
               & set(out["tools"])),
          "submit, export, check, list, pull, get, attach -- and nothing that authors data")

    print("\nPhase 6: the browser and the CLI (SPEC.md acceptance criterion 7)")
    node = shutil.which("node")
    harness = os.path.join(REPO, "web", "scripts", "pyodide-check.mjs")
    staged = os.path.join(REPO, "web", "public", "pyodide", "pyodide.mjs")
    if not (node and os.path.isfile(staged)):
        check("the browser path runs the same science as the CLI",
              False,
              "SKIPPED: needs node and a staged runtime -- run "
              "`cd web && npm install && npm run sync`")
    else:
        proc = subprocess.run([node, harness, "--json"], cwd=REPO,
                              capture_output=True, text=True)
        browser = json.loads(proc.stdout) if proc.returncode == 0 else None
        check("the whole round-4 loop runs in Pyodide, in the browser's own runtime",
              browser is not None and browser["round4"]["flagged"]
              and browser["decision"]["action"] == "apply_offset_correction",
              (("Python %s, numpy %s, %d ms"
                % (browser["python"], browser["numpy"], browser["timing"]["total_ms"]))
               if browser else (proc.stderr or "")[-200:]))
        if browser:
            snap4 = schema.read_json(os.path.join(demo, "evidence", "snapshot_004.json"))
            check("and it reproduces the committed round-4 numbers under a different numpy",
                  abs(browser["round4"]["mean_signed_residual"]
                      - snap4["anomaly"]["mean_signed_residual"]) < 5e-7
                  and abs(browser["round4"]["bridge_offset"]
                          - snap4["frame"]["offset_estimate"]["offset"]) < 5e-7,
                  "mean signed residual %.6f, bridge %.6f, against numpy %s on Python %s"
                  % (browser["round4"]["mean_signed_residual"],
                     browser["round4"]["bridge_offset"], browser["numpy"],
                     browser["python"]))
            check("approving a batch advances the round in under five seconds",
                  browser["timing"]["approve_ms"] < 5000
                  and browser["timing"]["advance_ms"] < 5000,
                  "approve %d ms, advance %d ms -- phase 6's done-condition"
                  % (browser["timing"]["approve_ms"], browser["timing"]["advance_ms"]))

            same, drifted = cli_replay_of(browser["files"])
            check("the browser and the CLI write byte-identical artifacts",
                  sorted(drifted) == ["decisions/decision_004.json", "rounds.json"],
                  "%d of %d files identical; the two that differ carry the time a person "
                  "ruled and the times the graph was rewritten"
                  % (len(same), len(same) + len(drifted)))
            check("including the next round's batch, which is criterion 7",
                  "batches/batch_005.json" in same,
                  "batch_005 %s on both surfaces"
                  % schema.short_hash(browser["after"]["round5_batch_hash"]))

            check("approving a round sends it to a lab rather than producing its data",
                  browser["submitted"]["status"] == "running"
                  and browser["first_check"]["ready"] is False
                  and browser["first_check"]["status"] == "running"
                  and bool(browser["first_check"]["expected"]),
                  "the first ask came back not ready, expected %s -- two moments with a "
                  "laboratory between them"
                  % (browser["first_check"]["expected"] or "?")[:10])
            check("and the round it eventually imports is the one it always was",
                  browser["round4"]["rows"] == 96
                  and browser["round4"]["n_censored"] == snap4["reconciliation"]["n_censored"]
                  and browser["round4"]["n_failed"] == snap4["reconciliation"]["n_failed"],
                  "%d rows, %d failed, %d censored -- staggering changes when the registry "
                  "hands them over, never what they are"
                  % (browser["round4"]["rows"], browser["round4"]["n_failed"],
                     browser["round4"]["n_censored"]))

            # The rounds that ran somewhere else. A session for one of them
            # used to be a title and a composer, because the command log is
            # the tab's and theirs is six weeks old on another machine.
            hist = browser["history"]
            check("a round that ran before this browser opened reads back out of its own "
                  "artifacts",
                  hist["past"] == [
                      ["proposed", "approved", "submitted", "returned", "scored", "fitted"],
                      ["proposed", "approved", "submitted", "returned", "scored", "fitted"],
                      ["proposed", "approved", "submitted", "returned", "scored", "frame",
                       "fitted"]]
                  and hist["pending"] == 0
                  and set(hist["reads"]) == {
                      "batches/batch_003.json", "candidates/pool_003.json", "designs.json",
                      "evidence/snapshot_003.json", "batches/batch_003.eval.json",
                      "models/run_003.json"},
                  "rounds 1 to 3 in %d steps from %d artifacts each; round 4, selected and "
                  "not sent, has nothing to read back"
                  % (len(hist["past"][2]), len(hist["reads"])))
            check("and every figure in it either names a core/ function that exists or "
                  "names none at all",
                  hist["resolve"] and all(f["found"] for f in hist["resolve"])
                  and all(f["artifact"] for f in hist["figures"]),
                  "%d of %d figures carry a source and all %d resolve; the rest were "
                  "computed inside a pipeline script and claim nothing"
                  % (len(hist["resolve"]), len(hist["figures"]), len(hist["resolve"])))

            lab = browser["lab"]
            check("the demo's clock is a control, and it is the only thing in the driver "
                  "that moves one",
                  lab["submitted"]["status"] == "running"
                  and lab["first_check"]["ready"] is False
                  and lab["released"]["status"] == "complete"
                  and lab["released"]["by"] == "the demo control"
                  and lab["reported"]["status"] == "results ready"
                  and lab["reported"]["reported"] is True
                  and lab["reported"]["at_lab"] is False
                  and lab["reported"]["needs_you"] == "results"
                  and lab["reported"]["landing"] == "r5"
                  and lab["reported"]["asks"][0] == "results_back",
                  "round 5 refused with %s, released by hand, and then waiting to be "
                  "pulled rather than waiting for approval"
                  % (lab["first_check"]["expected"] or "?")[:10])
            check("and the model can ask the registry itself, which is what the seat was "
                  "missing",
                  lab["tool"]["commands"] == ["registry: check_run_status",
                                              "registry: pull_assay_results",
                                              "import round 5",
                                              "score round 5 against its predictions"]
                  and lab["tool"]["ready"] and lab["tool"]["flagged"]
                  and lab["tool"]["rows"] == 96
                  and abs(lab["tool"]["mean_signed_residual"] + 0.818061) < 5e-7
                  and lab["tool"]["carries_no_commands"]
                  and lab["context"]["has_lab"],
                  "four commands from one tool call; round 5 comes back flagged at "
                  "%.6f pKD, the same number the product path gets"
                  % lab["tool"]["mean_signed_residual"])
            check("a round that came back quiet earns an ask only until it is carried "
                  "forward, and then it earns nothing",
                  lab["quiet"]["status"] == "imported"
                  and lab["quiet"]["flagged"] is False
                  and lab["quiet"]["asks"] == ["live", "agent"]
                  and lab["settled"]["status"] == "complete"
                  and lab["settled"]["asks"] == [],
                  "round 1 of a project created here: [%s] while the column is still "
                  "offering to fit it, [] once it has"
                  % ", ".join(lab["quiet"]["asks"]))
            check("it refuses a round already imported and a round never submitted, and "
                  "the refusal goes back as a result rather than ending the turn",
                  lab["tool_refusals"]["imported"]["refused"]
                  and lab["tool_refusals"]["imported"]["is_error"]
                  and "already imported" in lab["tool_refusals"]["imported"]["why"]
                  and lab["tool_refusals"]["unsubmitted"]["refused"]
                  and "has not been submitted" in lab["tool_refusals"]["unsubmitted"]["why"],
                  "a round comes back once: %s"
                  % lab["tool_refusals"]["imported"]["why"].split("; ")[0])

            made_same, made_drift = cli_instantiation_of(browser["files"])
            check("a project instantiated in the browser is one the CLI would have written",
                  sorted(made_drift) == ["rounds.json"] and len(made_same) == 5
                  and "project.json" in made_same and "objectives.json" in made_same
                  and "batches/batch_001.json" in made_same,
                  "%d of %d files identical, round 1 batch %s -- decision 108 in the form "
                  "a machine can check"
                  % (len(made_same), len(made_same) + len(made_drift),
                     schema.short_hash(browser["created"]["batch_hash"])))
            check("and round 1 went through the same two scripts every round goes through",
                  browser["created"]["mode"] == "seed"
                  and browser["created"]["n_designs"] == 48,
                  "%s, %d designs -- no batch written by a second code path"
                  % (browser["created"]["mode"], browser["created"]["n_designs"]))
            rl = browser.get("reload") or {}
            check("a project created in the browser survives the reload that follows it",
                  rl.get("dropped") == ["decisions", "evidence", "models"]
                  and rl.get("broke_before") is True and rl.get("lists_after") is True
                  and [r["project"] for r in rl.get("reasserted", [])]
                      == ["harness-instantiated"]
                  and rl["reasserted"][0]["created"] == ["decisions", "evidence", "models"],
                  "the overlay drops %d still-empty directories and the driver re-asserts "
                  "them at boot -- without it one created project takes the home list down "
                  "with it" % len(rl.get("dropped", [])))
            check("the status briefing is assembled from artifacts, not narrated",
                  browser["briefing"]["kind"] == "status"
                  and browser["briefing"]["source"] == "core.reconcile.pool"
                  and browser["briefing"]["model_winner"] == "ridge_onehot",
                  "best observed %s pKD via %s -- every figure names the function behind "
                  "it, which is what the Notebook tab resolves"
                  % (browser["briefing"]["best_observed"], browser["briefing"]["source"]))

            print("\nPhase 7: the agent in the session -- verified replay")
            v1 = browser["replay1"]["verified"]
            check("the recorded diagnosis is stepped with every test re-run here, and every "
                  "result matches the committed record by content hash",
                  browser["replay1"]["status"] == "done"
                  and v1["diagnostics"] == v1["of_diagnostics"] >= 8,
                  "%d of %d results match -- the badge's claim, checked"
                  % (v1["diagnostics"], v1["of_diagnostics"]))
            check("and every ad hoc cut runs again and prints what the record holds",
                  v1["ad_hoc"] == v1["of_ad_hoc"] >= 3,
                  "%d of %d cuts reproduce, from their source, read-only, in the sandbox"
                  % (v1["ad_hoc"], v1["of_ad_hoc"]))
            pb = browser["pushback"]
            check("the recorded push-back rules more_evidence_requested and the recorded "
                  "answer replays it (SPEC.md acceptance criterion 8, without a key)",
                  pb is not None and pb["ruled_status"] == "awaiting_evidence"
                  and pb["n_passes"] == 2 and pb["answering"] == pb["requested"]
                  and pb["replay_status"] == "done"
                  and pb["verified"]["diagnostics"] == pb["verified"]["of_diagnostics"] >= 1,
                  ("asked for %s; pass 2 answers it, %d of %d results match"
                   % (pb["requested"], pb["verified"]["diagnostics"],
                      pb["verified"]["of_diagnostics"])) if pb else "no recorded push-back")
            sg = browser.get("suggested") or {}
            check("the composer suggests nothing until the project's state earns it, and "
                  "a flagged round earns it (decisions 158 and 165)",
                  sg.get("awaiting_approval") == [] and sg.get("settled") == []
                  and sg.get("adhoc") == [] and sg.get("quiet") == []
                  and sg.get("seed") == []
                  and sg.get("flagged") == ["why_flagged", "whats_waiting", "agent"],
                  ("nothing on a batch awaiting approval, an ad-hoc session, or any of "
                   "rounds 1 to 3, which are settled; [%s] once round 4 flags, led by %r"
                   % (", ".join(sg.get("flagged", [])), sg.get("lead"))) if sg else "none")
            check("and every suggested ask is a prompt for the model, the agent's option "
                  "last, with the briefing still answering each keyed one without a seat",
                  sg.get("prompts") is True and sg.get("agent_last") is True
                  and sg.get("briefed") is True,
                  "each carries the text it sends; the no-key path still answers them")
            check("the context the model is handed is read from artifacts and fits the "
                  "cached prefix",
                  browser["context"]["rows"] == 48 and browser["context"]["decisions"] >= 2
                  and 20000 < browser["context"]["bytes"] < 160000
                  and "paths" in browser["context"]["keys"],
                  "%d bytes: objectives, the round graph, 48 scored wells, %d decision "
                  "records, and the paths an ad hoc cut may read"
                  % (browser["context"]["bytes"], browser["context"]["decisions"]))

            print("\nPhase 7: the live loop, through the function, scripted upstream")
            lv = browser["live"]
            check("the function is reachable in-process and reports its upstream honestly",
                  lv["probe"]["live"] is True and lv["probe"]["upstream"] == "scripted"
                  and lv["probe"]["store"] == "memory",
                  "live under a scripted upstream, memory budget store -- the harness, "
                  "labelled as the harness")
            check("a whole diagnosis round-trips: signed transcript, tool results answering "
                  "the model's calls, the proposal handed to the writer",
                  lv["pass1"]["status"] == "done" and lv["pass1"]["proposed"]
                  and lv["pass1"]["signed"] and lv["pass1"]["tool_steps"] >= 11
                  and lv["pass1"]["record"]["status"] == "open",
                  "%d tool calls over a %d-message transcript; %s recorded %s"
                  % (lv["pass1"]["tool_steps"], lv["pass1"]["transcript_messages"],
                     "decision_004", lv["pass1"]["record"]["status"]))
            check("and every number the loop wrote came from core/, recomputed here",
                  lv["pass1"]["verified"]["checked"]
                  and lv["pass1"]["verified"]["matched"] == lv["pass1"]["verified"]["total"] >= 8,
                  "%d of %d results in the written record match the reference by hash"
                  % (lv["pass1"]["verified"]["matched"], lv["pass1"]["verified"]["total"]))
            check("an edited transcript is refused before a token is spent",
                  lv["forged"]["status"] == 403,
                  "%d: %s" % (lv["forged"]["status"], lv["forged"]["error"]))
            ak = lv.get("ask")
            check("a question asked in the session continues the diagnosis's signed "
                  "transcript, answering its proposal first (decision 157)",
                  ak is not None and ak["status"] == "done" and not ak["restarted"]
                  and ak["continued"] and ak["answered_proposal"]
                  and ak["prior_turns_seen"] == ak["prior_turns"]
                  == lv["pass1"]["tool_steps"] + 1,
                  ("the model saw all %d earlier turns; the proposal's tool_result and the "
                   "question share one message; %d messages now"
                   % (ak["prior_turns"], ak["transcript_messages"])) if ak else "no ask")
            rs = lv.get("restart")
            check("a transcript the function will not accept starts the conversation over "
                  "rather than ending the turn, and the turn says why",
                  rs is not None and rs["status"] == "done" and rs["restarted"]
                  and rs["transcript_messages"] == 2,
                  ("done on a fresh 2-message transcript; restarted: %s" % rs["restarted"])
                  if rs else "no restart")
            check("a push-back continues the same signed transcript -- from the question, "
                  "not around it -- and writes pass 2",
                  lv.get("pass2") is not None and lv["pass2"]["continued"]
                  and lv["pass2"]["after_ask"]
                  and lv["pass2"]["record"]["n_passes"] == 2
                  and lv["pass2"]["record"]["answering"] == pb["requested"]
                  and lv["pass2"]["verified"]["matched"] == lv["pass2"]["verified"]["total"],
                  ("%d messages, pass 2 answers %s, %d of %d results match"
                   % (lv["pass2"]["transcript_messages"], lv["pass2"]["record"]["answering"],
                      lv["pass2"]["verified"]["matched"], lv["pass2"]["verified"]["total"]))
                  if lv.get("pass2") else "no pass 2")

    print("\nPhase 7: the function is not a proxy for the Claude API")
    asker = os.path.join(REPO, "web", "scripts", "ask-check.mjs")
    if not node:
        check("the function refuses what it must", False, "SKIPPED: needs node")
    else:
        proc = subprocess.run([node, asker, "--json"], cwd=REPO, capture_output=True, text=True)
        fnr = json.loads(proc.stdout) if proc.returncode == 0 else None
        check("the function answers its probe without a key, and says so",
              fnr is not None and fnr["probe"]["live"] is False
              and fnr["probe"]["reason"] == "no key configured"
              and fnr["probe"]["upstream"] == "anthropic",
              (fnr["probe"]["reason"] if fnr else (proc.stderr or "")[-200:]))
        if fnr:
            ref = fnr["refusals"]
            check("it refuses a forged transcript, an oversized context, a test outside the "
                  "library, a model outside the allowlist, and a result nobody asked for",
                  ref["forged_transcript"]["status"] == 403
                  and ref["oversized_context"]["status"] == 413
                  and ref["test_outside_library"]["status"] == 400
                  and ref["unknown_model"]["status"] == 400
                  and ref["results_with_nothing_pending"]["status"] == 400
                  and ref["ruling_names_no_library_test"]["status"] == 400
                  and fnr["wrong_tool_id_status"] == 400,
                  "403, 413, 400, 400, 400, 400, 400 -- each before a token could be spent")
            check("and a transcript it signed is accepted right up to the key",
                  fnr["signed_accepted_status"] == 503
                  and ref["well_formed_but_no_key"]["status"] == 503,
                  "503 no key configured: validation passed, nothing was sent")
            qp = fnr["question_on_proposal"]
            check("a question that continues a proposal must carry the proposal's tool "
                  "result, and then it is one message with the result first",
                  qp["without_result"] == 400 and qp["with_result"] == 503
                  and qp["shape"] == ["tool_result", "text"] and qp["messages"] == 3,
                  "400 without it, 503 with it; the third message is [tool_result, text]")
            rq = fnr["request"]
            check("the request it builds is fixed: model allowlisted, effort low, adaptive "
                  "thinking, fallbacks on, the context block cached",
                  rq["model"] == "claude-sonnet-5" and rq["effort"] == "low"
                  and rq["thinking"] == "adaptive" and rq["fallbacks"] == "default"
                  and rq["betas"] == ["server-side-fallback-2026-07-01"]
                  and rq["context_cached"] and rq["max_tokens"] == 16000,
                  "%s, effort %s, max_tokens %d, fallbacks %s"
                  % (rq["model"], rq["effort"], rq["max_tokens"], rq["fallbacks"]))
            hk = fnr["haiku_request"]
            check("and the one model that predates adaptive thinking is asked without it",
                  hk["model"] == "claude-haiku-4-5-20251001"
                  and hk["has_thinking"] is False and hk["has_effort"] is False
                  and hk["fallbacks"] == "default" and hk["betas"] == rq["betas"]
                  and hk["max_tokens"] == rq["max_tokens"]
                  and hk["tools"] == rq["tools"]
                  and hk["system_blocks"] == rq["system_blocks"],
                  "Haiku 4.5 rejects both fields by name; everything else about its "
                  "request -- prompt, tools, cap, fallbacks -- is the other model's")
            check("the model is offered two read tools, the registry, and one way to hand "
                  "back, and no way to name a test the template does not permit",
                  rq["tools"] == ["run_diagnostic", "execute_analysis",
                                  "check_lab_results", "propose_decision"]
                  and rq["ask_tools"] == ["run_diagnostic", "execute_analysis",
                                          "check_lab_results"]
                  and rq["chat_tools"] == []
                  and rq["run_diagnostic_enum"] == list(diagnostics.TESTS)
                  and rq["run_diagnostic_strict"],
                  "two reads, the registry, and one way to hand back; run_diagnostic's "
                  "enum is the context's permitted list, strict; a chat gets no tools")
            check("its system prompt is the skill itself",
                  rq["system_has_skill"] and rq["system_blocks"] == 3
                  and fnr["probe"]["skill_sha256"] == hashlib.sha256(
                      open(os.path.join(REPO, "skills", "adaptive-optimization", "SKILL.md"),
                           "rb").read()).hexdigest(),
                  "SKILL.md sha256 %s, as the function carries it -- one file drives Claude "
                  "Code, Claude Science and the browser" % fnr["probe"]["skill_sha256"][:12])
            ac = fnr["access_code"]
            check("with an access code configured, the live seat is closed to a call that "
                  "does not carry it, and the probe says so",
                  ac["probe_without"]["live"] is False
                  and ac["probe_without"]["reason"] == "no access code"
                  and ac["probe_without"]["code_required"] is True
                  and ac["probe_wrong"]["reason"] == "access code not recognised"
                  and ac["probe_right"]["reason"] == "no key configured"
                  and ac["call_without"] == 401 and ac["call_wrong"] == 401
                  and ac["call_right"] == 503,
                  "401 without it, 401 with the wrong one, 503 with the right one -- the "
                  "code is checked before anything else, and the right one goes as far as "
                  "the key")
            rv = fnr["reservation"]
            check("a call reserves its maximum before it is made, so a burst cannot pass "
                  "the cap on a stale read",
                  rv["burst_admitted"] == 3 and rv["burst_refused"] == 5
                  and rv["burst_reason"] == "daily budget spent"
                  and abs(rv["spent_after_settle"] - 0.15) < 1e-6
                  and rv["in_flight_after_settle"] == 0
                  and rv["crowd_seated"] == 2
                  and rv["crowd_reason"] == "the seat is busy; try again in a moment"
                  and abs(rv["spent_after_release"] - 0.15) < 1e-6
                  and rv["in_flight_after_release"] == 0
                  and rv["calls_after_release"] == 3,
                  "8 at once against $1: 3 admitted at $0.30 and 5 refused; settled to "
                  "$%.2f; 2 of 5 seated under an in-flight cap of 2; released clean"
                  % rv["spent_after_settle"])

    print("\nPhase 7: the committed record is two-pass, and the second pass is a gate's")
    p1, p2 = dec4["passes"][0], (dec4["passes"][1] if dec4["n_passes"] > 1 else None)
    check("pass 1 was sent back by a named person, naming a library test",
          p1["ruling"] is not None and p1["ruling"]["verdict"] == "more_evidence_requested"
          and p1["ruling"]["by"] and p1["ruling"]["requested"]["diagnostic"] in diagnostics.TESTS
          and len(p1["ruling"]["note"].split()) > 20,
          "%s asked for %s" % (p1["ruling"]["by"] if p1["ruling"] else "nobody",
                               p1["ruling"]["requested"]["diagnostic"] if p1["ruling"] else "-"))
    check("pass 2 answers it: it ran what was asked for and proposed again",
          p2 is not None and p2["answering"] == p1["ruling"]["requested"]["diagnostic"]
          and any(h["diagnostic"] == p2["answering"] for h in p2["hypotheses"])
          and p2["recommendation"]["action"] in
          ("apply_offset_correction", "drop_wells", "refit_only", "no_action")
          and len(p2["recommendation"]["if_wrong"].split()) > 20,
          ("%d hypotheses, recommends %s, confidence %s"
           % (len(p2["hypotheses"]), p2["recommendation"]["action"],
              p2["recommendation"]["confidence"])) if p2 else "no second pass")
    check("and the final ruling is left to a person, so the round still waits",
          p2 is not None and p2["ruling"] is None and dec4["status"] == "open",
          "both passes committed; the verdict is not")
    check("the push-back gate's transcript is committed beside the other two",
          os.path.isfile(os.path.join(REPO, "gates", "pushback-round4.md"))
          and os.path.isfile(os.path.join(REPO, "gates", "pushback-round4.jsonl")),
          "gates/pushback-round4.md")

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
