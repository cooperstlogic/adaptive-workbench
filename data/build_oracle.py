"""Generate the landscape once, calibrate it to the pre-registered target, and
write the assets.

Run from the repo root:  python -m data.build_oracle
"""

import json
import os
import sys

import numpy as np

from core import candidates, encode, schema
from data import synthetic

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(REPO, "templates", "antibody-affinity-maturation", "template.json")
OUT_NPZ = os.path.join(REPO, "data", "landscape.npz")
OUT_BIN = os.path.join(REPO, "web", "public", "assets", "oracle.bin")
OUT_MANIFEST = os.path.join(REPO, "data", "landscape_manifest.json")


def build(verbose=True):
    tpl = schema.read_json(TEMPLATE)
    parent = tpl["lead"]["sequence"]
    region = tpl["lead"]["editable_region"]
    max_mut = tpl["constraints"]["max_mutations"]

    pool = candidates.enumerate_variants(parent, region, max_mut)
    land = synthetic.Landscape(parent, region, synthetic.PARAMS)
    beta = land.calibrate(pool)
    values = land.value(pool)
    r2 = land.realized_linear_r2(pool)

    detection_limit = float(np.percentile(values, synthetic.PARAMS["detection_limit_percentile"]))

    # The gate, as a fraction of the climb from the parent to the landscape
    # maximum. Amended 2026-09-20 from the pre-registered 99th percentile; the
    # amendment block below carries the superseded rule and its value so the
    # manifest alone is enough to see what changed.
    parent_value = float(land.value([parent])[0])
    climb = float(values.max()) - parent_value
    threshold = parent_value + synthetic.PARAMS["threshold_climb_fraction"] * climb
    superseded = float(np.percentile(values, 99.0))

    np.savez_compressed(
        OUT_NPZ,
        additive=land.additive, pairwise=land.pairwise,
        beta=np.array([beta]), cliff_j=np.array([land.cliff_j]),
        values=values.astype(np.float32),
    )
    os.makedirs(os.path.dirname(OUT_BIN), exist_ok=True)
    values.astype(np.float32).tofile(OUT_BIN)

    manifest = {
        "schema_version": schema.SCHEMA_VERSION,
        "unit": schema.UNIT,
        "params": synthetic.PARAMS,
        "parent": parent,
        "editable_region": region,
        "n_candidates": len(pool),
        "derived": {
            "beta": beta,
            "realized_linear_r2": r2,
            "cliff_position": land.cliff_position,
            "cliff_window_index": land.cliff_j,
            "cliff_parent_residue": parent[land.cliff_position],
            "cliff_residues": "".join(land.cliff_aa),
            "detection_limit_pkd": detection_limit,
            "threshold_pkd": threshold,
            "parent_pkd": float(land.value([parent])[0]),
            "landscape_max_pkd": float(values.max()),
            "landscape_min_pkd": float(values.min()),
            "landscape_median_pkd": float(np.median(values)),
        },
        "amendments": [
            {
                "date": "2026-09-20",
                "field": "derived.threshold_pkd",
                "from": {"rule": "99th percentile of the enumerated pool",
                         "param": "threshold_percentile = 99.0",
                         "threshold_pkd": round(superseded, 5)},
                "to": {"rule": "fraction of the parent-to-maximum climb",
                       "param": "threshold_climb_fraction = %s"
                                % synthetic.PARAMS["threshold_climb_fraction"],
                       "threshold_pkd": round(threshold, 5)},
                "pre_registered": False,
                "after_seeing_results": True,
                "reason": ("The pre-registered gate sat 66% of the way from the parent to "
                           "the landscape maximum, low enough that a blind 48-well draw "
                           "cleared it 39% of the time and guided hit it at round 2 in every "
                           "seed. Rounds-to-threshold was therefore ceiling-limited: both "
                           "arms had a median of 2.0 and 12 of 20 paired seeds tied. The new "
                           "rule sits above the additive ceiling reachable from the round-1 "
                           "scan, so the metric has resolution."),
                "authorized_by": "Dylan Webster",
                "note": ("Chosen after inspecting a sweep of candidate thresholds over the "
                         "completed runs. This is an amendment and not a pre-registration; "
                         "the separation it reports is not protected by the commit order "
                         "that protects the rest of this manifest."),
            },
        ],
    }
    manifest["build_hash"] = schema.content_hash(manifest)
    schema.write_json(OUT_MANIFEST, manifest)

    if verbose:
        d = manifest["derived"]
        print("candidates      %d" % len(pool))
        print("beta            %.4f  (realized linear R2 %.4f, target %.2f)"
              % (beta, r2, synthetic.PARAMS["target_linear_r2"]))
        print("cliff           position %d (window idx %d), parent %s, residues %s, depth %.2f"
              % (d["cliff_position"], d["cliff_window_index"], d["cliff_parent_residue"],
                 d["cliff_residues"], synthetic.PARAMS["cliff_depth"]))
        print("parent pKD      %.3f" % d["parent_pkd"])
        print("landscape       min %.3f  median %.3f  max %.3f"
              % (d["landscape_min_pkd"], d["landscape_median_pkd"], d["landscape_max_pkd"]))
        print("detection limit %.3f  (p%.0f)" % (d["detection_limit_pkd"], synthetic.PARAMS["detection_limit_percentile"]))
        print("THRESHOLD       %.3f  (%.0f%% of the parent-to-max climb; AMENDED 2026-09-20,"
              " superseding the pre-registered p99 at %.3f)"
              % (d["threshold_pkd"], 100 * synthetic.PARAMS["threshold_climb_fraction"],
                 manifest["amendments"][0]["from"]["threshold_pkd"]))
        print("build hash      %s" % manifest["build_hash"])
    return manifest


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
