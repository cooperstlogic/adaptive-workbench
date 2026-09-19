#!/usr/bin/env python3
"""Verify the repo's invariants. Run after a fresh clone, and before trusting
any phase that builds on an earlier one.

    python check.py

Every check here corresponds to a rule in CLAUDE.md or a number recorded in
DECISIONS.md. A failure means the state has drifted from what is documented,
not that a test is being fussy.
"""

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

    from core import candidates, encode, project, schema, scoring
    from data import synthetic
    from data.oracle import Oracle, assay_version

    man = schema.read_json(os.path.join(REPO, "data", "landscape_manifest.json"))
    d = man["derived"]

    print("\nBoundaries (CLAUDE.md non-negotiables 1, 2, 4)")
    src = []
    for root, _, files in os.walk(os.path.join(REPO, "core")):
        for f in files:
            if f.endswith(".py"):
                src.append(open(os.path.join(root, f)).read())
    blob = "\n".join(src)
    check("core/ imports no simulated lab, no network",
          not any(t in blob for t in ("import data", "from data", "import requests", "import urllib", "import socket")))
    check("core/ does not print", "\nprint(" not in blob and not blob.startswith("print("))
    check("core/ uses no scipy, sklearn or pandas",
          not any(t in blob for t in ("scipy", "sklearn", "pandas")))

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
