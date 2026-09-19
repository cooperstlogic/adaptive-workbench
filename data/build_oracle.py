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
    threshold = float(np.percentile(values, synthetic.PARAMS["threshold_percentile"]))

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
        print("THRESHOLD       %.3f  (p%.0f, fixed before any campaign run)"
              % (d["threshold_pkd"], synthetic.PARAMS["threshold_percentile"]))
        print("build hash      %s" % manifest["build_hash"])
    return manifest


if __name__ == "__main__":
    sys.exit(0 if build() else 1)
