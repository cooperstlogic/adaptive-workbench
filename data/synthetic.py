"""The synthetic landscape: additive site effects, pairwise epistasis, one cliff.

Not an NK model, and the reason is decisive: with ``max_mutations = 2`` only
first- and second-order terms are ever reachable from the parent, so a model
with higher-order interactions would carry terms that can never fire. Pairwise
is exactly expressive enough.

Every parameter here was pre-registered and committed before this file first
ran -- the table is in README.md under "Pre-registered landscape parameters",
and non-negotiable 9 in CLAUDE.md is the rule.
"""

import numpy as np

from core import encode

PARAMS = {
    "seed": 20260918,
    "parent_pkd": 9.00,
    "additive_sigma": 0.45,
    "target_linear_r2": 0.60,
    "cliff_residues": "PDEKR",
    "cliff_depth": -1.50,
    "assay_noise_sigma": 0.15,
    "round_offset_sigma": 0.10,
    "plate_offset_sigma": 0.05,
    "round4_version_shift": -0.80,
    "construct_failure_rate": 0.03,
    "reads_per_design": 2,
    "detection_limit_percentile": 2.0,
    "threshold_percentile": 99.0,
}


class Landscape:
    """pKD as a function of sequence. Ground truth; no product path may read it."""

    def __init__(self, parent, editable_region, params=None):
        self.parent = parent
        self.editable_region = list(editable_region)
        self.params = dict(PARAMS if params is None else params)
        self.sl = encode.region_slice(editable_region)
        self.L = encode.region_length(editable_region)
        self.positions = list(range(self.sl.start, self.sl.stop))
        rng = np.random.default_rng(self.params["seed"])

        # Additive site effects, zeroed at the parent residue so the parent sits
        # exactly at parent_pkd.
        self.additive = rng.normal(0.0, self.params["additive_sigma"], size=(self.L, encode.N_AA))
        for j, pos in enumerate(self.positions):
            self.additive[j, encode.AA_INDEX[parent[pos]]] = 0.0

        # Pairwise interactions, zeroed whenever either residue is the parent's,
        # so epistasis only fires between two actual mutations.
        self.pairwise = rng.normal(0.0, 1.0, size=(self.L, self.L, encode.N_AA, encode.N_AA))
        for j, pj in enumerate(self.positions):
            for k, pk in enumerate(self.positions):
                if k <= j:
                    self.pairwise[j, k, :, :] = 0.0
                    continue
                self.pairwise[j, k, encode.AA_INDEX[parent[pj]], :] = 0.0
                self.pairwise[j, k, :, encode.AA_INDEX[parent[pk]]] = 0.0

        # Cliff position by the pre-registered rule: the editable position with
        # the largest maximum additive effect, so the optimizer is drawn to it
        # naturally rather than by construction.
        self.cliff_j = int(np.argmax(self.additive.max(axis=1)))
        self.cliff_position = self.positions[self.cliff_j]
        self.cliff_aa = tuple(sorted(self.params["cliff_residues"]))
        self.beta = 1.0  # calibrated by calibrate()

    # --- components ---------------------------------------------------------

    def _indices(self, sequences):
        idx = np.empty((len(sequences), self.L), dtype=np.int64)
        for r, s in enumerate(sequences):
            for j, pos in enumerate(self.positions):
                idx[r, j] = encode.AA_INDEX[s[pos]]
        return idx

    def linear_part(self, sequences):
        """Additive effects plus the cliff. Both are single-site, so this is
        exactly what a one-hot linear model can represent -- which is why the
        cliff is learnable, and therefore diagnosable."""
        idx = self._indices(sequences)
        out = self.additive[np.arange(self.L)[None, :], idx].sum(axis=1)
        cliff_col = idx[:, self.cliff_j]
        is_cliff = np.isin(cliff_col, [encode.AA_INDEX[a] for a in self.cliff_aa])
        return out + is_cliff * self.params["cliff_depth"]

    def epistatic_part(self, sequences):
        idx = self._indices(sequences)
        n = len(sequences)
        out = np.zeros(n)
        for j in range(self.L):
            for k in range(j + 1, self.L):
                out += self.pairwise[j, k, idx[:, j], idx[:, k]]
        return out

    def value(self, sequences):
        if isinstance(sequences, str):
            sequences = [sequences]
        return (
            self.params["parent_pkd"]
            + self.linear_part(sequences)
            + self.beta * self.epistatic_part(sequences)
        )

    def carries_cliff(self, sequences):
        idx = self._indices(sequences)
        return np.isin(idx[:, self.cliff_j], [encode.AA_INDEX[a] for a in self.cliff_aa])

    # --- calibration --------------------------------------------------------

    def calibrate(self, pool, tol=0.002, iters=60):
        """Solve beta so a one-hot linear model explains the pre-registered
        fraction of variance. The target is pre-registered in README.md; only beta
        moves, and it moves to hit that number -- not to hit a result."""
        target = self.params["target_linear_r2"]
        A = self.linear_part(pool)
        B = self.epistatic_part(pool)
        vA, vB = float(np.var(A)), float(np.var(B))
        lo, hi = 0.0, max(1e-6, np.sqrt(vA * (1.0 / target - 1.0) / max(vB, 1e-12))) * 8.0
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            self.beta = mid
            r2 = self.realized_linear_r2(pool)
            if abs(r2 - target) < tol:
                break
            if r2 > target:
                lo = mid
            else:
                hi = mid
        return self.beta

    def realized_linear_r2(self, pool):
        """R^2 of an actual one-hot least-squares fit over the whole pool."""
        X = encode.one_hot(pool, self.editable_region).astype(np.float64)
        X = np.hstack([X, np.ones((X.shape[0], 1))])
        y = self.value(pool)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X @ coef
        return float(1.0 - np.var(resid) / np.var(y))
